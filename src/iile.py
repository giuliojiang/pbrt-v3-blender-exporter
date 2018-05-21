bl_info = {
    "name": "PBRTv3 Exporter",
    "category": "Render"
}

import bpy
from bl_ui import (
    properties_render,
    properties_material,
    properties_data_camera
)
from bpy.types import Menu, Panel
import os
import subprocess
import math
import time

DEFAULT_IILE_PROJECT_PATH = "/home/gj/git/pbrt-v3-IISPT/build"

# Utilities ===============================================================================

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

# Scene parser ===================================================================================

TABSIZE = 4

def lineIndentTabs(l):
    count = 0
    for c in l:
        if c == ' ':
            count += 1
        else:
            break
    if (count % TABSIZE) != 0:
        return 0
    return count / TABSIZE

def indentBy(l, levels):
    idt = ""
    for i in range(TABSIZE * levels):
        idt += " "
    return idt + l

# A block is a collection of lines part of a logical block,
# for example in MakeNamedMaterial or in AttributeBegin
class SceneBlock():

    def __init__(self, lines):
        self.lines = lines

    # Returns the string representation for writing to file
    # There is no trailing \n
    def toString(self):
        return "\n".join(self.lines)

    # Returns None if this type of block is not recognized
    def getBlockType(self):
        if len(self.lines) == 0:
            return None
        first = self.lines[0]
        splt = first.split(" ")
        if len(splt) != 0:
            return splt[0]
        else:
            return None

    # Replaces a line content
    # if the line is at the specified <level> of indentation
    # and if it starts with <startMatch>
    def replaceLine(self, level, startMatch, newStr):
        for i in range(len(self.lines)):
            l = self.lines[i]
            if lineIndentTabs(l) == level:
                rawLine = l[(TABSIZE * level):]
                if rawLine.startswith(startMatch):
                    transformedLine = indentBy(newStr, level)
                    self.lines[i] = transformedLine

    # Matching function
    def contains(self, level, startMatch):
        for i in range(len(self.lines)):
            l = self.lines[i]
            if lineIndentTabs(l) == level:
                rawLine = l[(TABSIZE * level):]
                if rawLine.startswith(startMatch):
                    return True
        return False

    def findLine(self, level, startMatch):
        for i in range(len(self.lines)):
            l = self.lines[i]
            if lineIndentTabs(l) == level:
                rawLine = l[(TABSIZE * level):]
                if rawLine.startswith(startMatch):
                    return rawLine
        return None

    # Finds AttributeBegin->AreaLightSource blocks
    def isAreaLightSource(self):
        return (self.getBlockType() == "AttributeBegin") and (self.contains(1, "AreaLightSource"))

    def isMakeNamedMaterial(self):
        return self.getBlockType() == "MakeNamedMaterial"

    def getMaterialDefinitionName(self):
        first = self.lines[0].rstrip()
        splt = first.split(" ")
        return " ".join(splt[1:]).replace('"', '')

    def clearBody(self):
        if len(self.lines) >= 1:
            self.lines = self.lines[0:1]

    def getAssignedMaterial(self):
        if self.getBlockType() == "AttributeBegin":
            line = self.findLine(1, "NamedMaterial")
            splt = line.split(" ")
            if len(splt) > 0:
                selection = splt[1:]
                return " ".join(selection).replace('"', '')
            else:
                return None
        else:
            return None

    def appendLine(self, level, content):
        self.lines.append(indentBy(content, level))

# Represents the entire parsed scenefile
class SceneDocument():

    def __init__(self):
        self.blocks = []

    def parse(self, filepath):
        f = open(filepath, "r")

        sceneBlocks = []
        currentBlock = []

        for line in f:
            line = line[:-1]
            if lineIndentTabs(line) > 0:
                currentBlock.append(line)
            else:
                # Collect previous block
                if len(currentBlock) > 0:
                    sceneBlocks.append(SceneBlock(currentBlock))
                # Start a new block
                currentBlock = []
                currentBlock.append(line)

        # Collect last block
        if len(currentBlock) > 0:
            sceneBlocks.append(SceneBlock(currentBlock))

        f.close()

        self.blocks = sceneBlocks

    def getBlocks(self):
        return self.blocks

    def write(self, outPath):
        outFile = open(outPath, 'w')
        for block in self.blocks:
            outFile.write("{}\n".format(block.toString()))
        outFile.close()

# Scene parser end =============================================================

# Render engine ================================================================================

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
        pbrtExecPath = os.path.join(scene.iilePath, "pbrt")
        obj2pbrtExecPath = os.path.join(scene.iilePath, "obj2pbrt")
        rootDir = os.path.abspath(os.path.join(scene.iilePath, ".."))

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

        # Create headers and footers -------------------------------------------------
        outSceneFile = open(outScenePath, "w")

        # Create headers

        wline(outSceneFile, 'Film "image" "integer xresolution" {} "integer yresolution" {}'.format(sx, sy))

        integratorName = "path"
        if bpy.context.scene.iileIntegrator == "PATH":
            integratorName = "path"
        elif bpy.context.scene.iileIntegrator == "IILE":
            integratorName = "iispt"
        else:
            raise Exception("Unrecognized iileIntegrator {}".format(
                bpy.context.scene.iileIntegrator))
        wline(outSceneFile, 'Integrator "{}"'.format(integratorName))

        samplerName = "random"
        if bpy.context.scene.iileIntegratorPathSampler == "RANDOM":
            samplerName = "random"
        elif bpy.context.scene.iileIntegratorPathSampler == "SOBOL":
            samplerName = "sobol"
        elif bpy.context.scene.iileIntegratorPathSampler == "HALTON":
            samplerName = "halton"
        else:
            raise Exception("Unrecognized sampler {}".format(bpy.context.scene.iileIntegratorPathSampler))

        wline(outSceneFile, 'Sampler "{}" "integer pixelsamples" {}'.format(samplerName, bpy.context.scene.iileIntegratorPathSamples))

        wline(outSceneFile, 'Scale -1 1 1')

        # Get camera
        theCameraName = bpy.context.scene.camera.name
        theCamera = bpy.data.cameras[theCameraName]

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

        # Write camera fov
        wline(outSceneFile, 'Camera "perspective" "float fov" [{}]'.format(math.degrees(theCamera.angle / 2.0)))

        # TODO write film size

        # Write world begin
        wline(outSceneFile, 'WorldBegin')

        # Copy content from outExp2Pbrt
        appendFile(outExp2PbrtPath, outSceneFile)

        # Write world end
        wline(outSceneFile, 'WorldEnd')

        outSceneFile.close()

        # -----------------------------------------------------------
        # Scene transformation
        doc = SceneDocument()
        doc.parse(outScenePath)
        blocks = doc.getBlocks()

        for block in blocks:

            # Set area light emission color
            if block.isAreaLightSource():
                print("Processing an area light source")
                matName = block.getAssignedMaterial()
                print(matName)
                matObj = bpy.data.materials[matName]
                emitIntensity = matObj.emit
                emitColor = [0.0, 0.0, 0.0]
                emitColor[0] = emitIntensity * matObj.iileEmission[0]
                emitColor[1] = emitIntensity * matObj.iileEmission[1]
                emitColor[2] = emitIntensity * matObj.iileEmission[2]
                block.replaceLine(3, '"rgb L"',
                    '"rgb L" [ {} {} {} ]'.format(
                        emitColor[0], emitColor[1], emitColor[2]))

            # Set material properties
            if block.isMakeNamedMaterial():
                matName = block.getMaterialDefinitionName()
                print("Processing material {}".format(matName))
                matObj = bpy.data.materials[matName]
                block.clearBody()
                # Write material type
                # MATTE
                if matObj.iileMaterial == "MATTE":
                    block.appendLine(2, '"string type" "matte"')
                    # Diffuse color
                    block.appendLine(2, '"rgb Kd" [ {} {} {} ]' \
                        .format(matObj.iileMatteColor[0],
                            matObj.iileMatteColor[1],
                            matObj.iileMatteColor[2]))
                else:
                    raise Exception("Unrecognized material {}".format(
                        matObj.iileMaterial))


        doc.write(outScenePath)

        print("Rendering finished.")

        if (bpy.context.scene.iileIntegrator == "IILE") and bpy.context.scene.iileStartRenderer:
            print("Starting IILE GUI...")
            guiDir = os.path.join(rootDir, "gui")
            electronPath = os.path.join(guiDir,
                "node_modules",
                "electron",
                "dist",
                "electron")
            jsPbrtPath = os.path.join(rootDir,
                "bin",
                "pbrt")
            cmd = []
            cmd.append(electronPath)
            cmd.append("main.js")
            cmd.append(jsPbrtPath)
            cmd.append(outScenePath)
            cmd.append("{}".format(bpy.context.scene.iileIntegratorIileIndirect))
            cmd.append("{}".format(bpy.context.scene.iileIntegratorIileDirect))
            runCmd(cmd, cwd=guiDir)

        result = self.begin_result(0, 0, sx, sy)
        self.end_result(result)

# UI elements =======================================================

class RENDER_PT_output(properties_render.RenderButtonsPanel, Panel):
    bl_label = "Output"
    COMPAT_ENGINES = {IILERenderEngine.bl_idname}

    def draw(self, context):
        layout = self.layout
        rd = context.scene.render
        layout.prop(rd, "filepath", text="Exporter output directory")

class RENDER_PT_iile(properties_render.RenderButtonsPanel, Panel):
    bl_label = "PBRT Build Path"
    COMPAT_ENGINES = {IILERenderEngine.bl_idname}

    def draw(self, context):
        layout = self.layout

        s = context.scene
        layout.prop(s, "iilePath", text="PBRT binaries directory")

        layout.prop(s, "iileIntegrator", text="Integrator")

        if bpy.context.scene.iileIntegrator == "IILE":
            layout.prop(s, "iileStartRenderer", text="Autostart IILE GUI")
            layout.prop(s, "iileIntegratorIileIndirect", text="Indirect")
            layout.prop(s, "iileIntegratorIileDirect", text="Direct")

        elif bpy.context.scene.iileIntegrator == "PATH":
            layout.prop(s, "iileIntegratorPathSampler", text="Sampler")
            layout.prop(s, "iileIntegratorPathSamples", text="Samples")

        else:
            raise Exception("Unsupported integrator {}".format(bpy.context.scene.iileIntegrator))

class MATERIAL_PT_material(properties_material.MaterialButtonsPanel, Panel):
    bl_label = "Material"
    COMPAT_ENGINES = {IILERenderEngine.bl_idname}

    def draw(self, context):
        layout = self.layout

        mat = properties_material.active_node_mat(context.material)

        layout.prop(mat, "iileMaterial", text="Surface type")

        if mat.iileMaterial == "MATTE":
            layout.prop(mat, "iileMatteColor", text="Diffuse color")

class MATERIAL_PT_emission(properties_material.MaterialButtonsPanel, Panel):
    bl_label = "Emission"
    COMPAT_ENGINES = {IILERenderEngine.bl_idname}

    def draw(self, context):
        layout = self.layout

        mat = properties_material.active_node_mat(context.material)

        layout.prop(mat, "emit", text="Emission Intensity")

        layout.prop(mat, "iileEmission", text="Emission color")

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

    Scene.iileStartRenderer = bpy.props.BoolProperty(
        name="Start IILE renderer",
        description="Automatically start IILE renderer after exporting. Not compatible with vanilla PBRTv3",
        default=False
    )

    Scene.iileIntegrator = bpy.props.EnumProperty(
        name="Integrator",
        description="Surface Integrator",
        items=[
            ("PATH", "Path", "Path Integrator"),
            ("IILE", "IILE", "IILE Integrator")
        ]
    )

    Scene.iileIntegratorIileIndirect = bpy.props.IntProperty(
        name="Indirect Tasks",
        description="Number of IILE Indirect Tasks to be executed",
        default=16,
        min=0
    )

    Scene.iileIntegratorIileDirect = bpy.props.IntProperty(
        name="Direct Samples",
        description="Number of Direct Illumination samples",
        default=16,
        min=1
    )

    Scene.iileIntegratorPathSampler = bpy.props.EnumProperty(
        name="Sampler",
        description="Sampler",
        items=[
            ("RANDOM", "Random", "Random Sampler"),
            ("SOBOL", "Sobol", "Sobol Sampler"),
            ("HALTON", "Halton", "Halton Sampler")
        ]
    )

    Scene.iileIntegratorPathSamples = bpy.props.IntProperty(
        name="Samples",
        description="Number of samples/px",
        default=4,
        min=1
    )

    Mat = bpy.types.Material

    Mat.iileMaterial = bpy.props.EnumProperty(
        name="IILE Material",
        description="Material type",
        items=[
            ("MATTE", "Matte", "Lambertian Diffuse Material")
        ]
    )

    Mat.iileMatteColor = bpy.props.FloatVectorProperty(
        name="Diffuse color",
        description="Diffuse color",
        subtype="COLOR",
        precision=4,
        step=0.01,
        min=0.0,
        soft_max=1.0,
        default=(0.75, 0.75, 0.75)
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

    # Camera
    properties_data_camera.DATA_PT_lens.COMPAT_ENGINES.add(IILERenderEngine.bl_idname)


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
