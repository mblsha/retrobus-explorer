from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import cadquery as cq
from cadquery import exporters
from shapely import affinity
from shapely.geometry import MultiPolygon, Polygon
from shapely.geometry.base import BaseGeometry

from mechanical.layout import (
    ROUND_QUADRANTS,
    ForgeLayout,
    ForgeParameters,
    Hole,
    build_layout,
    clearance_estimates,
    hole_geometry,
    mirror_holes_for_press,
)
from src.geometry import BOARD_HEIGHT, BOARD_WIDTH


def polygon_faces(geometry: BaseGeometry, z: float) -> list[cq.Face]:
    if geometry.is_empty:
        return []
    polygons: list[Polygon] = []
    if isinstance(geometry, Polygon):
        polygons = [geometry]
    elif isinstance(geometry, MultiPolygon):
        polygons = list(geometry.geoms)
    else:
        for part in geometry.geoms:  # type: ignore[attr-defined]
            if isinstance(part, Polygon):
                polygons.append(part)
            elif isinstance(part, MultiPolygon):
                polygons.extend(part.geoms)

    faces = []
    for polygon in polygons:
        outer = cq.Wire.makePolygon(
            [cq.Vector(float(x), float(y), z) for x, y in list(polygon.exterior.coords)[:-1]],
            close=True,
        )
        inner_wires = [
            cq.Wire.makePolygon(
                [cq.Vector(float(x), float(y), z) for x, y in list(interior.coords)[:-1]],
                close=True,
            )
            for interior in polygon.interiors
        ]
        faces.append(cq.Face.makeFromWires(outer, inner_wires))
    return faces


def extrude_geometry(geometry: BaseGeometry, z: float, height: float) -> cq.Shape:
    solids = [
        cq.Solid.extrudeLinear(
            face.outerWire(),
            face.innerWires(),
            cq.Vector(0.0, 0.0, height),
        )
        for face in polygon_faces(geometry, z)
    ]
    if not solids:
        raise RuntimeError("Cannot extrude empty geometry")
    if len(solids) == 1:
        return solids[0]
    return cq.Compound.makeCompound(solids)


def make_spikes(holes: tuple[Hole, ...], z: float, height: float, clearance: float) -> cq.Shape:
    spike_solids = []
    for hole in holes:
        radius = (hole.diameter - clearance) / 2.0
        spike_solids.append(
            cq.Solid.makeCone(
                radius,
                min(0.15, radius * 0.4),
                height,
                cq.Vector(hole.center[0], hole.center[1], z),
                cq.Vector(0.0, 0.0, 1.0),
            )
        )
    return cq.Compound.makeCompound(spike_solids)


def build_models(layout: ForgeLayout, parameters: ForgeParameters) -> tuple[cq.Shape, cq.Shape]:
    parameters.validate()

    pcb_base = extrude_geometry(layout.base_profile, 0.0, parameters.board_thickness)
    channel_tool = extrude_geometry(
        layout.top_copper,
        parameters.board_thickness - parameters.trace_depth,
        parameters.trace_depth + 0.05,
    )
    pcb_base = pcb_base.cut(channel_tool)
    drill_tool = extrude_geometry(hole_geometry(layout.holes), -0.05, parameters.board_thickness + 0.10)
    pcb_base = pcb_base.cut(drill_tool)

    press_plate = extrude_geometry(layout.outer_profile, 0.0, parameters.press_plate_thickness)
    mirrored_top_copper = affinity.scale(
        layout.top_copper,
        xfact=-1.0,
        yfact=1.0,
        origin=(0.0, 0.0),
    )
    press_relief_2d = mirrored_top_copper.buffer(
        -parameters.press_clearance / 2.0,
        quad_segs=ROUND_QUADRANTS,
    )
    press_relief = extrude_geometry(
        press_relief_2d,
        parameters.press_plate_thickness,
        parameters.ridge_height,
    )
    spikes = make_spikes(
        mirror_holes_for_press(layout.holes),
        parameters.press_plate_thickness,
        parameters.spike_height,
        parameters.spike_clearance,
    )
    press_form = press_plate.fuse(press_relief).fuse(spikes)

    for name, shape in (("PCB base", pcb_base), ("press form", press_form)):
        if not shape.isValid():
            raise RuntimeError(f"{name} is not a valid solid")
        if shape.Volume() <= 0.0:
            raise RuntimeError(f"{name} has no volume")
    return pcb_base, press_form


def svg_path(geometry: BaseGeometry) -> str:
    polygons = [geometry] if isinstance(geometry, Polygon) else list(geometry.geoms)  # type: ignore[attr-defined]
    path_parts = []
    for polygon in polygons:
        if not isinstance(polygon, Polygon):
            continue
        for ring in (polygon.exterior, *polygon.interiors):
            coords = list(ring.coords)
            path_parts.append("M " + " L ".join(f"{x:.5f},{y:.5f}" for x, y in coords) + " Z")
    return " ".join(path_parts)


def write_svg(output: Path, layout: ForgeLayout, *, ground_mask: str | None) -> None:
    view_box = f"{-BOARD_WIDTH / 2.0} {-BOARD_HEIGHT / 2.0} {BOARD_WIDTH} {BOARD_HEIGHT}"
    if ground_mask == "front":
        contents = f'<path d="{svg_path(layout.front_ground_foil)}" fill="#b87333" fill-rule="evenodd"/>'
        title = "Front GND copper foil cutting mask"
    elif ground_mask == "bottom":
        contents = f'<path d="{svg_path(layout.ground_foil)}" fill="#b87333" fill-rule="evenodd"/>'
        title = "Bottom GND copper foil cutting mask"
    else:
        contents = "\n".join(
            [
                f'<path d="{svg_path(layout.base_profile)}" fill="#3d5e4f" fill-rule="evenodd"/>',
                f'<path d="{svg_path(layout.top_copper)}" fill="#b87333" fill-rule="evenodd"/>',
                f'<path d="{svg_path(hole_geometry(layout.holes))}" fill="#ffffff" fill-rule="evenodd"/>',
            ]
        )
        title = "PCB Forge top-copper layout"
    output.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="UTF-8"?>',
                (
                    f'<svg xmlns="http://www.w3.org/2000/svg" width="{BOARD_WIDTH}mm" '
                    f'height="{BOARD_HEIGHT}mm" viewBox="{view_box}">'
                ),
                f"  <title>{title}</title>",
                '  <g transform="scale(1,-1)">',
                f"    {contents}",
                "  </g>",
                "</svg>",
            ]
        )
        + "\n"
    )


def export_model(
    shape: cq.Shape,
    stl_output: Path,
    step_output: Path | None,
    tolerance: float,
) -> None:
    exporters.export(
        shape,
        str(stl_output),
        exportType="STL",
        tolerance=tolerance,
        angularTolerance=0.10,
    )
    if step_output is not None:
        exporters.export(shape, str(step_output), exportType="STEP")


def render_preview(output: Path, pcb_base_stl: Path, press_form_stl: Path) -> None:
    import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
    from vtkmodules.vtkFiltersCore import vtkPolyDataNormals
    from vtkmodules.vtkIOGeometry import vtkSTLReader
    from vtkmodules.vtkIOImage import vtkPNGWriter
    from vtkmodules.vtkRenderingCore import (
        vtkActor,
        vtkPolyDataMapper,
        vtkRenderer,
        vtkRenderWindow,
        vtkWindowToImageFilter,
    )

    renderer = vtkRenderer()
    renderer.SetBackground(0.933, 0.941, 0.965)

    def add_model(path: Path, color: tuple[float, float, float], x_offset: float) -> None:
        reader = vtkSTLReader()
        reader.SetFileName(str(path))
        normals = vtkPolyDataNormals()
        normals.SetInputConnection(reader.GetOutputPort())
        normals.SetFeatureAngle(35.0)
        normals.SplittingOn()
        mapper = vtkPolyDataMapper()
        mapper.SetInputConnection(normals.GetOutputPort())
        actor = vtkActor()
        actor.SetMapper(mapper)
        actor.SetPosition(x_offset, 0.0, 0.0)
        actor.GetProperty().SetColor(*color)
        actor.GetProperty().SetAmbient(0.24)
        actor.GetProperty().SetDiffuse(0.76)
        actor.GetProperty().SetSpecular(0.12)
        actor.GetProperty().SetSpecularPower(18.0)
        renderer.AddActor(actor)

    add_model(pcb_base_stl, (0.20, 0.42, 0.33), -44.0)
    add_model(press_form_stl, (0.86, 0.50, 0.20), 44.0)

    render_window = vtkRenderWindow()
    render_window.SetOffScreenRendering(1)
    render_window.SetSize(1400, 900)
    render_window.AddRenderer(renderer)

    camera = renderer.GetActiveCamera()
    camera.SetFocalPoint(0.0, 0.0, 1.5)
    camera.SetPosition(142.0, -180.0, 150.0)
    camera.SetViewUp(0.0, 0.0, 1.0)
    camera.ParallelProjectionOn()
    camera.SetParallelScale(70.0)
    renderer.ResetCameraClippingRange()
    render_window.Render()

    capture = vtkWindowToImageFilter()
    capture.SetInput(render_window)
    capture.SetInputBufferTypeToRGBA()
    capture.ReadFrontBufferOff()
    capture.Update()
    writer = vtkPNGWriter()
    writer.SetFileName(str(output))
    writer.SetInputConnection(capture.GetOutputPort())
    writer.Write()


def shape_summary(shape: cq.Shape) -> dict[str, object]:
    bounds = shape.BoundingBox()
    return {
        "valid": shape.isValid(),
        "volume_mm3": round(shape.Volume(), 4),
        "bounds_mm": {
            "x": [round(bounds.xmin, 4), round(bounds.xmax, 4)],
            "y": [round(bounds.ymin, 4), round(bounds.ymax, 4)],
            "z": [round(bounds.zmin, 4), round(bounds.zmax, 4)],
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a PCB Forge-style printable PCB base and companion press form"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).with_name("pcb-forge"),
    )
    parser.add_argument("--board-thickness", type=float, default=ForgeParameters.board_thickness)
    parser.add_argument("--trace-depth", type=float, default=ForgeParameters.trace_depth)
    parser.add_argument("--press-plate-thickness", type=float, default=ForgeParameters.press_plate_thickness)
    parser.add_argument("--ridge-height", type=float, default=ForgeParameters.ridge_height)
    parser.add_argument("--press-clearance", type=float, default=ForgeParameters.press_clearance)
    parser.add_argument("--spike-height", type=float, default=ForgeParameters.spike_height)
    parser.add_argument("--spike-clearance", type=float, default=ForgeParameters.spike_clearance)
    parser.add_argument("--stl-tolerance", type=float, default=ForgeParameters.stl_tolerance)
    parser.add_argument(
        "--include-step",
        action="store_true",
        help="also export large editable STEP files; CadQuery source remains the default editable format",
    )
    parser.add_argument("--skip-preview", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    parameters = ForgeParameters(
        board_thickness=args.board_thickness,
        trace_depth=args.trace_depth,
        press_plate_thickness=args.press_plate_thickness,
        ridge_height=args.ridge_height,
        press_clearance=args.press_clearance,
        spike_height=args.spike_height,
        spike_clearance=args.spike_clearance,
        stl_tolerance=args.stl_tolerance,
    )
    parameters.validate()
    layout = build_layout()
    pcb_base, press_form = build_models(layout, parameters)

    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = "pico-plus-2-uln2003-forge-pcb-base"
    press_name = "pico-plus-2-uln2003-forge-press-form"
    base_stl = output_dir / f"{base_name}.stl"
    base_step = output_dir / f"{base_name}.step"
    press_stl = output_dir / f"{press_name}.stl"
    press_step = output_dir / f"{press_name}.step"
    top_svg = output_dir / "pico-plus-2-uln2003-forge-top-layout.svg"
    front_ground_svg = output_dir / "pico-plus-2-uln2003-front-ground-foil-mask.svg"
    ground_svg = output_dir / "pico-plus-2-uln2003-bottom-ground-foil-mask.svg"
    preview_png = output_dir / "pico-plus-2-uln2003-forge-preview.png"
    manifest_path = output_dir / "manifest.json"

    export_model(pcb_base, base_stl, base_step if args.include_step else None, parameters.stl_tolerance)
    export_model(press_form, press_stl, press_step if args.include_step else None, parameters.stl_tolerance)
    if not args.include_step:
        base_step.unlink(missing_ok=True)
        press_step.unlink(missing_ok=True)
    write_svg(top_svg, layout, ground_mask=None)
    write_svg(front_ground_svg, layout, ground_mask="front")
    write_svg(ground_svg, layout, ground_mask="bottom")
    if not args.skip_preview:
        render_preview(preview_png, base_stl, press_stl)

    manifest = {
        "generator": Path(__file__).name,
        "units": "mm",
        "parameters": asdict(parameters),
        "layout": {
            "board_size_mm": [BOARD_WIDTH, BOARD_HEIGHT],
            "through_holes": len(layout.holes),
            "top_copper_nets": len(layout.top_nets),
            "top_copper_area_mm2": round(layout.top_copper.area, 4),
            "front_ground_foil_area_mm2": round(layout.front_ground_foil.area, 4),
            "bottom_ground_foil_area_mm2": round(layout.ground_foil.area, 4),
        },
        "models": {
            "pcb_base": shape_summary(pcb_base),
            "press_form": shape_summary(press_form),
        },
        "parameter_clearance_estimates": clearance_estimates(parameters),
        "files": {
            "pcb_base_stl": base_stl.name,
            "press_form_stl": press_stl.name,
            "top_layout_svg": top_svg.name,
            "front_ground_foil_mask_svg": front_ground_svg.name,
            "bottom_ground_foil_mask_svg": ground_svg.name,
            **(
                {
                    "pcb_base_step": base_step.name,
                    "press_form_step": press_step.name,
                }
                if args.include_step
                else {}
            ),
            **({"preview_png": preview_png.name} if not args.skip_preview else {}),
        },
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        f"Wrote PCB base, press form, copper layouts, and manifest to {output_dir} "
        f"({len(layout.holes)} holes; {len(layout.top_nets)} top nets)"
    )


if __name__ == "__main__":
    main()
