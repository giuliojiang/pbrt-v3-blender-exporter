bl_info = {
    "name": "PBRTv3 Exporter",
    "category": "Render"
}

import bpy
from bl_ui import (
    properties_render,
    properties_material,
)
from bpy.types import Menu, Panel
import os
import subprocess
import math
import time

DEFAULT_IILE_PROJECT_PATH = "/home/gj/git/pbrt-v3-IISPT"

def runCmd(cmd, stdout=None, cwd=None):
    stdoutInfo = ""
    if stdout is not None:
        stdoutInfo = " > {}".format(stdout.name)
    print(">>> {}{}".format(cmd, stdoutInfo))
    subprocess.call(cmd, shell=False, stdout=stdout, cwd=cwd)

def wline(f, t):
    f.write("{}\n".format(t))

def appendFile(sourcePath, destFile):
    sourceFile = open(sourcePath, 'r')
    for line in sourceFile:
        destFile.write(line)
    sourceFile.close()

class IILERenderEngine(bpy.types.RenderEngine):
    bl_idname = "iile_renderer" # internal name
    bl_label = "IILE Renderer" # Visible name
    bl_use_preview = False # capabilities

    def render(self, scene):

        scale = scene.render.resolution_percentage / 100.0
        sx = int(scene.render.resolution_x * scale)
        sy = int(scene.render.resolution_y * scale)

        print("Starting render, resolution {} {}".format(sx, sy))

        # Compute pbrt executale path
        pbrtExecPath = os.path.join(scene.iilePath, "build", "pbrt")
        obj2pbrtExecPath = os.path.join(scene.iilePath, "build", "obj2pbrt")

        # Get the output path
        outDir = bpy.data.scenes["Scene"].render.filepath
        outDir = bpy.path.abspath(outDir)
        print("Out dir is {}".format(outDir))
        outObjPath = os.path.join(outDir, "exp.obj")
        outExpPbrtPath = os.path.join(outDir, "exp.pbrt")
        outExp2PbrtPath = os.path.join(outDir, "exp2.pbrt")
        outScenePath = os.path.join(outDir, "scene.pbrt")

        # Create exporting script
        expScriptPath = os.path.join(outDir, "exp.py")
        expScriptFile = open(expScriptPath, "w")
        wline(expScriptFile, 'import bpy')
        wline(expScriptFile, 'outobj = "{}"'.format(outObjPath))
        wline(expScriptFile, 'bpy.ops.export_scene.obj(filepath=outobj, axis_forward="Y", axis_up="-Z", use_materials=True)')
        expScriptFile.close()

        blenderPath = bpy.app.binary_path
        projectPath = bpy.data.filepath

        cmd = [
            blenderPath,
            projectPath,
            "--background",
            "--python",
            expScriptPath
        ]
        runCmd(cmd)

        print("OBJ export completed")

        # Run obj2pbrt
        cmd = [
            obj2pbrtExecPath,
            outObjPath,
            outExpPbrtPath
        ]
        runCmd(cmd, cwd=outDir)

        # Run pbrt --toply
        cmd = [
            pbrtExecPath,
            "--toply",
            outExpPbrtPath
        ]
        outExp2PbrtFile = open(outExp2PbrtPath, "w")
        runCmd(cmd, stdout=outExp2PbrtFile, cwd=outDir)
        outExp2PbrtFile.close()

        # Create headers and footers
        outSceneFile = open(outScenePath, "w")

        # Create headers
        wline(outSceneFile, 'Integrator "path"')
        wline(outSceneFile, 'Sampler "sobol" "integer pixelsamples" 1')
        wline(outSceneFile, 'Scale -1 1 1')

        # Write camera rotation
        cameraRotationAmount = bpy.context.scene.camera.rotation_axis_angle[0]
        cameraRotationAmount = math.degrees(cameraRotationAmount)
        cameraRotationX, cameraRotationY, cameraRotationZ = \
            bpy.context.scene.camera.rotation_axis_angle[1:]
        # Flip Y
        cameraRotationY = -cameraRotationY
        wline(outSceneFile, 'Rotate {} {} {} {}'.format(
            cameraRotationAmount, cameraRotationX,
            cameraRotationY, cameraRotationZ))

        # Write camera translation
        cameraLocX, cameraLocY, cameraLocZ = bpy.context.scene.camera.location
        # Flip Y
        cameraLocY = -cameraLocY
        wline(outSceneFile, 'Translate {} {} {}'.format(
            cameraLocX, cameraLocY, cameraLocZ))

        # Write camera perspective
        # TODO read fov from properties
        wline(outSceneFile, 'Camera "perspective" "float fov" 70')

        # TODO write film size

        # Write world begin
        wline(outSceneFile, 'WorldBegin')

        # Copy content from outExp2Pbrt
        appendFile(outExp2PbrtPath, outSceneFile)

        # Write world end
        wline(outSceneFile, 'WorldEnd')

        outSceneFile.close()

        print("Rendering finished.")
        result = self.begin_result(0, 0, sx, sy)
        self.end_result(result)

# UI elements =======================================================

class RENDER_PT_output(properties_render.RenderButtonsPanel, Panel):
    bl_label = "Output"
    COMPAT_ENGINES = {IILERenderEngine.bl_idname}

    def draw(self, context):
        layout = self.layout
        rd = context.scene.render
        layout.prop(rd, "filepath", text="")

class RENDER_PT_iile(properties_render.RenderButtonsPanel, Panel):
    bl_label = "PBRT Build Path"
    COMPAT_ENGINES = {IILERenderEngine.bl_idname}

    def draw(self, context):
        layout = self.layout
        s = context.scene
        layout.prop(s, "iilePath", text="")

class MATERIAL_PT_material(properties_material.MaterialButtonsPanel, Panel):
    bl_label = "Material"
    COMPAT_ENGINES = {IILERenderEngine.bl_idname}

    def draw(self, context):
        layout = self.layout

        mat = properties_material.active_node_mat(context.material)

        layout.prop(mat, "iileMaterial", text="material")

        if mat.iileMaterial == "DIFFUSE":
            layout.prop(mat, "diffuse_color", text="")

class MATERIAL_PT_emission(properties_material.MaterialButtonsPanel, Panel):
    bl_label = "Emission"
    COMPAT_ENGINES = {IILERenderEngine.bl_idname}

    def draw(self, context):
        layout = self.layout

        mat = properties_material.active_node_mat(context.material)

        layout.prop(mat, "emit", text="emission")

        layout.prop(mat, "iileEmission", text="emission color")

# Register ==================================================================

def register():
    bpy.utils.register_class(IILERenderEngine)

    # Add properties -------------------------------------------------------

    Scene = bpy.types.Scene

    Scene.iilePath = bpy.props.StringProperty(
        name="PBRT build path",
        description="Directory that contains the pbrt executable",
        default=DEFAULT_IILE_PROJECT_PATH
    )

    Mat = bpy.types.Material

    Mat.iileMaterial = bpy.props.EnumProperty(
        name="IILE Material",
        description="Material type",
        items=[
            ("DIFFUSE", "Diffuse", "Lambertian Diffuse Material")
        ]
    )

    Mat.iileEmission = bpy.props.FloatVectorProperty(
        name="IILE Emission",
        description="Color of the emission",
        subtype="COLOR",
        precision=4,
        step=0.01,
        min=0.0,
        soft_max=1.0,
        default=(1, 1, 1)
    )

    # UI -------------------------------------------------------------

    # Render Button
    properties_render.RENDER_PT_render.COMPAT_ENGINES.add(IILERenderEngine.bl_idname)
    # Dimensions
    properties_render.RENDER_PT_dimensions.COMPAT_ENGINES.add(
        IILERenderEngine.bl_idname)
    # Output
    bpy.utils.register_class(RENDER_PT_output)
    # IILE Settings
    bpy.utils.register_class(RENDER_PT_iile)

    # Material slots
    properties_material.MATERIAL_PT_context_material.COMPAT_ENGINES.add(IILERenderEngine.bl_idname)
    # Material type
    bpy.utils.register_class(MATERIAL_PT_material)
    # Material emission
    bpy.utils.register_class(MATERIAL_PT_emission)


def unregister():
    bpy.utils.unregister_class(IILERenderEngine)

    from bl_ui import (
        properties_render,
        properties_material,
        )
    properties_render.RENDER_PT_render.COMPAT_ENGINES.remove(IILERenderEngine.bl_idname)
    properties_material.MATERIAL_PT_preview.COMPAT_ENGINES.remove(
        IILERenderEngine.bl_idname)

if __name__ == "__main__":
    register()
