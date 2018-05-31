import bpy
import os
import shutil

globalTextureCounter = 0

def makeNewTextureName(extension):
    global globalTextureCounter
    globalTextureCounter += 1
    return "tex_{}{}".format(globalTextureCounter, extension)

def addTexture(texSource, outDir, block):
    texAbsPath = bpy.path.abspath(texSource)
    baseName = os.path.basename(texAbsPath)
    stem, ext = os.path.splitext(baseName)
    destName = makeNewTextureName(ext)
    destPath = os.path.join(outDir, destName)
    shutil.copyfile(texAbsPath, destPath)
    # Add the texture to the block
    textureLine = 'Texture "{}" "color" "imagemap" "string filename" "{}"'.format(destName, destName)
    block.addBeginning(0, textureLine)
    return destName