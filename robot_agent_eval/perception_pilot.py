"""Matched recorded-frame E1/E2/E4 pilot, with real accounted Astra and SAM3.

This measures latency and geometric agreement, NOT localization accuracy or
robot success. Independent object ground truth is deliberately unavailable.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import time
import numpy as np
from PIL import Image
from .common import ROOT, read, write, sha
from .proxy import ModelProxy
from .react_harness import ResponsesClient, image_content, object_schema
from .ablation_perception import LocalSAM, load_recorded_camera, locate, fit_target, project, backproject


def seed_payload(camera, state, image_path, config):
    vector = dict(type='array', items={'type': 'number'}, minItems=3, maxItems=3)
    pixel = dict(type='array', items={'type': 'integer'}, minItems=2, maxItems=2)
    schema = object_schema(dict(found={'type': 'boolean'}, arm={'type': 'string', 'enum': ['left', 'right']},
        target_prompt={'type': 'string'}, grasp_pixel=pixel, axis_pixels=dict(type='array', items=pixel, minItems=2, maxItems=2),
        estimated_world_xyz=vector, evidence={'type': 'string'}))
    text = dict(instruction=state['instruction'], state=state['state'], camera='cam_head',
        image_shape=list(camera['color'].shape[:2]), intrinsic_matrix=camera['intrinsic_matrix'].tolist(),
        camera_to_world_USD=camera['extrinsic_matrix'].tolist())
    return dict(model=config['model'], reasoning={'effort': config['reasoning_effort']},
        instructions='Select the instructed object and a graspable part from RGB. For a shovel choose a narrow shaft, '
        'not the blade or D grip. Pixels are [row,col] in the ORIGINAL image. Supply two points along the local '
        'part axis. target_prompt must be a short object category noun such as "shovel"; '
        'omit color, material and shape modifiers for this local SAM prompt. '
        'Estimate the grasp point in world metres from RGB and public calibration; no depth is supplied. '
        'USD camera looks along -Z, +Y up. Do not claim the XYZ estimate is measured. '
        'If not visible set found=false. This is an observation query; do not move the robot.',
        input=[dict(role='user', content=[dict(type='input_text', text=json.dumps(text, allow_nan=False)),
            image_content(image_path, max(camera['color'].shape[:2]))])],
        tools=[dict(type='function', name='select_target', strict=True, parameters=schema)],
        tool_choice={'type': 'function', 'name': 'select_target'}, parallel_tool_calls=False,
        max_output_tokens=config.get('max_output_tokens_per_request', 8192), store=False, stream=False)


def select_target(client, camera, state, image_path, config):
    before = time.perf_counter()
    response = client.request(seed_payload(camera, state, image_path, config))
    if response.get('status') != 'completed' or response.get('model') != config['model']:
        raise RuntimeError('Incomplete or wrong-model selection')
    calls = [x for x in response['output'] if x.get('type') == 'function_call' and x.get('name') == 'select_target']
    if len(calls) != 1:
        raise ValueError('Expected one select_target call')
    result = json.loads(calls[0]['arguments'])
    if not result['found']:
        raise ValueError('Astra could not identify a visible grasp target')
    for pixel in [result['grasp_pixel'], *result['axis_pixels']]:
        p = np.asarray(pixel)
        if p.shape != (2,) or not np.isfinite(p).all() or np.any(p < 0) or np.any(p >= camera['color'].shape[:2]):
            raise ValueError('Astra pixel outside original image')
    if not np.isfinite(result['estimated_world_xyz']).all():
        raise ValueError('Nonfinite RGB XYZ estimate')
    return result, time.perf_counter()-before


def offline_geometry_audit(camera):
    depth = camera.get('distance_to_image_plane', camera.get('depth')).squeeze()
    uv = np.argwhere(np.isfinite(depth) & (depth > 0))[::997]
    points = backproject(camera, uv)
    reprojection, d = project(camera, points)
    return dict(points=len(points), max_roundtrip_px=float(np.max(np.abs(reprojection-uv))),
                max_depth_roundtrip_m=float(np.max(np.abs(d-depth[uv[:, 0], uv[:, 1]]))),
                scope='Algebraic consistency only, not external camera calibration accuracy')


def run(directories, config_path, output, selection_record=None):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    config = read(config_path)
    if config['wire_api'] != 'responses' or config.get('allow_model_fallback'):
        raise ValueError('Fixed Responses configuration required')
    manifest = dict(stage='E1/E2/E4 recorded-frame engineering pilot', frame_sources=[str(Path(d).resolve()) for d in directories],
        model=config['model'], reasoning_effort=config['reasoning_effort'], config_sha256=sha(config_path),
        source_sha256={n: sha(ROOT/'robot_agent_eval'/n) for n in ('ablation_perception.py', 'perception_pilot.py')},
        scoring='No object ground truth; XYZ differences are agreement, not accuracy',
        sam_checkpoint_identity=read(ROOT/'results/sam3-download.json'))
    recorded = None
    if selection_record:
        recorded = read(Path(selection_record)/'results.json')
        manifest['selection_origin'] = str(Path(selection_record).resolve())
        if len(recorded) != len(directories):
            raise ValueError('Selection/frame count mismatch')
    write(output/'manifest.json', manifest)
    proxy = ModelProxy(config, output/'model_requests.jsonl') if recorded is None else None
    prior_url = os.environ.get('ROBOT_REACT_PROXY_URL')
    if proxy:
        os.environ['ROBOT_REACT_PROXY_URL'] = proxy.start()
    client = ResponsesClient(config, output) if proxy else None
    rows = []
    try:
        # Astra runs on matched recorded frames. Preserve all failures.
        for index, directory in enumerate(directories):
            directory = Path(directory); d = output/f'frame-{index:03d}'; d.mkdir()
            camera = load_recorded_camera(directory)
            state = read(directory/'state.json')
            row = dict(index=index, source=str(directory), rgb_sha256=sha(directory/'cam_head.png'),
                       rgbd_sha256=sha(directory/'public_rgbd.npz'), audit=offline_geometry_audit(camera))
            try:
                if recorded is None:
                    seed, elapsed = select_target(client, camera, state, directory/'cam_head.png', config)
                else:
                    old = recorded[index]
                    if old['rgb_sha256'] != row['rgb_sha256'] or old['rgbd_sha256'] != row['rgbd_sha256']:
                        raise ValueError('Recorded selection does not match sensor hashes')
                    seed, elapsed = old['astra'], old['astra_elapsed_s']
                    row['selection_reused'] = True
                row.update(astra=seed, astra_elapsed_s=elapsed)
                write(d/'seed.json', seed)
                local_start = time.perf_counter()
                row['point_depth'] = locate(camera, seed['grasp_pixel'])
                row['median_depth'] = locate(camera, seed['grasp_pixel'], estimator='median')
                row['depth_geometry_elapsed_s'] = time.perf_counter()-local_start
                row['rgb_vs_depth_agreement_m'] = float(np.linalg.norm(np.asarray(seed['estimated_world_xyz'])-
                                                                    row['point_depth']['world_xyz']))
            except Exception as error:
                row['astra_or_geometry_error'] = dict(type=type(error).__name__, message=str(error))
            rows.append(row); write(output/'results.json', rows)
        sam = LocalSAM(ROOT/'checkpoints/sam3/sam3.pt')
        write(output/'sam_runtime.json', dict(load_s=sam.load_s))
        initial_seed = next((r.get('astra') for r in rows if r.get('astra')), None)
        tracked_xyz = None
        for row, directory in zip(rows, directories):
            camera = load_recorded_camera(directory)
            d = output/f'frame-{row["index"]:03d}'
            if not row.get('astra'):
                continue
            # E4 uses the SAME current Astra seed and SAM mask across estimators.
            try:
                mask, receipt = sam.segment(camera['color'], point=row['astra']['grasp_pixel'])
                Image.fromarray(mask.astype(np.uint8)*255).save(d/'sam-current-seed.png')
                row['sam_point'] = receipt
                row['masked_median'] = locate(camera, row['astra']['grasp_pixel'], mask=mask, estimator='median')
                row['masked_cloud'] = locate(camera, row['astra']['grasp_pixel'], mask=mask, estimator='cloud')
                geometry, cloud = fit_target(camera, mask, row['astra']['grasp_pixel'])
                row['local_axis_fit'] = geometry
                np.save(d/'target_cloud.npy', cloud)
            except Exception as error:
                row['sam_or_geometry_error'] = dict(type=type(error).__name__, message=str(error))
            # E2: one initial semantic selection, then project tracked XYZ to
            # the next camera and segment there. No subsequent Astra seed used.
            if initial_seed:
                try:
                    pixel = (project(camera, [tracked_xyz])[0][0].round().astype(int).tolist()
                             if tracked_xyz is not None else initial_seed['grasp_pixel'])
                    mask, receipt = sam.segment(camera['color'], point=pixel)
                    geometry, _ = fit_target(camera, mask, pixel)
                    tracked_xyz = geometry['world_xyz']
                    row['one_seed_local_updates'] = dict(seed_pixel=pixel, sam=receipt, geometry=geometry)
                    Image.fromarray(mask.astype(np.uint8)*255).save(d/'sam-one-seed.png')
                except Exception as error:
                    row['one_seed_local_error'] = dict(type=type(error).__name__, message=str(error))
            write(output/'results.json', rows)
        write(output/'summary.json', dict(frames=len(rows), astra_successful_frames=sum('astra' in r for r in rows),
            sam_geometry_frames=sum('local_axis_fit' in r for r in rows),
            one_seed_local_frames=sum('one_seed_local_updates' in r for r in rows),
            astra_wait_s=sum(r.get('astra_elapsed_s', 0) for r in rows),
            sam_current_seed_s=sum(r.get('sam_point', {}).get('elapsed_s', 0) for r in rows),
            model_requests_this_run=client.calls if client else 0,
            interpretation='Matched recorded snapshots; not independent layouts, grasp trials, or measured localization accuracy'))
    except Exception as error:
        write(output/'failure.json', dict(type=type(error).__name__, message=str(error)))
        raise
    finally:
        if proxy:
            proxy.close()
        if prior_url is None:
            os.environ.pop('ROBOT_REACT_PROXY_URL', None)
        else:
            os.environ['ROBOT_REACT_PROXY_URL'] = prior_url
    return output


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--frames', type=Path, nargs='+', required=True)
    p.add_argument('--config', type=Path, default=ROOT/'configs/model.react-pilot.json')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--selection-record', type=Path, help='Reuse hash-matched paid selections; retain their original provenance')
    args = p.parse_args()
    print(run(args.frames, args.config, args.output, args.selection_record), flush=True)


if __name__ == '__main__':
    main()
