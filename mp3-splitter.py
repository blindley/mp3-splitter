#!/bin/env python3

from codecs import utf_8_decode
from curses.ascii import isblank
import os, subprocess

groupingsFilename = 'groupings.txt'
step2InstructionsFilename = 'step2-instructsions.txt'
processCompleteFilename = 'chapterization-complete.txt'

def isAudioFile(filename):
    audioFileExtensions = ['mp3', 'm4a', 'm4b']
    for ext in audioFileExtensions:
        if filename.endswith(f'.{ext}'):
            return True
    return False

def getInputAudioFiles(dir='.'):
    for filename in os.listdir(dir):
        if isAudioFile(filename):
            yield os.path.join(dir, filename)

def isSamePath(p1, p2):
    return os.path.normpath(p1) == os.path.normpath(p2)

def concatAudioFiles(inputFileList, outputFile):
    concatListFilename = 'concat-list.txt'
    with open(concatListFilename, 'w') as concatListFile:
        for inp in inputFileList:
            line = f"file '{inp}'\n"
            concatListFile.write(line)

    DEVNULL = subprocess.DEVNULL

    ffmpegArgs = [
        'ffmpeg', '-f', 'concat', '-safe', '0', '-i', concatListFilename, outputFile,
    ]
    subprocess.call(ffmpegArgs, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL, shell=False)
    os.remove(concatListFilename)

def detectSilence(audioFile):
    DEVNULL = subprocess.DEVNULL

    ffmpegArgs = [
        'ffmpeg', '-i', audioFile, '-af', 'silencedetect=n=-30dB:d=0.5',
        '-f', 'null', '-'
    ]
    processResult = subprocess.run(ffmpegArgs, capture_output=True, stdin=DEVNULL)
    outputLines = processResult.stderr.decode().splitlines()
    outputLines = [l for l in outputLines if l.startswith('[silencedetect @')]

    expectingSilenceStart = False
    expectingSilenceEnd = False
    silenceInterval = [None, None]
    silenceIntervalList = []
    for word in processResult.stderr.decode().split():
        if expectingSilenceStart:
            silenceInterval[0] = float(word)
            expectingSilenceStart = False
        elif expectingSilenceEnd:
            silenceInterval[1] = float(word)
            expectingSilenceEnd = False
            silenceIntervalList.append(silenceInterval)
            silenceInterval = [None, None]
        elif word == 'silence_start:':
            expectingSilenceStart = True
        elif word == 'silence_end:':
            expectingSilenceEnd = True

    return silenceIntervalList

def makeSplitPointsFromIntervals(intervalList):
    splitPointList = []
    for int_ in intervalList:
        intervalDuration = int_[1] - int_[0]
        splitPoint = int_[1] - 0.5
        if intervalDuration < 1.0:
            splitPoint = int_[0] + intervalDuration / 2.0
        splitPointList.append(splitPoint)
    return splitPointList

def splitAudio(inputAudioFile, splitPointList, outputPattern):
    DEVNULL = subprocess.DEVNULL

    commaSeparatedSplitPoints = ','.join([str(n) for n in splitPointList])

    ffmpegArgs = [
        'ffmpeg', '-v', 'error', '-i', inputAudioFile, '-f', 'segment',
        '-segment_times', commaSeparatedSplitPoints, outputPattern
    ]
    subprocess.call(ffmpegArgs, stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL, shell=False)



def step1():
    concatAudioFilename = 'concat.mp3'

    if not os.path.exists(concatAudioFilename):
        inputFiles = [f for f in getInputAudioFiles() if not isSamePath(f, concatAudioFilename)]
        concatAudioFiles(inputFiles, concatAudioFilename)
        for inp in inputFiles:
            os.remove(inp)

    print('done with concatenation')

    silenceIntervalList = detectSilence(concatAudioFilename)
    silenceIntervalList.sort(key=lambda int_ : int_[1] - int_[0], reverse=True)
    splitPointList = makeSplitPointsFromIntervals(silenceIntervalList[:99])

    splitPointList.sort()

    splitAudio(concatAudioFilename, splitPointList, "%02d.mp3")
    os.remove(concatAudioFilename)



def groupAndSplitEvenly(groupFileList, groupDirectoryName):
    concatAudioFilename = os.path.join(groupDirectoryName, 'concat.mp3')
    concatAudioFiles(groupFileList, concatAudioFilename)
    silenceIntervalList = detectSilence(concatAudioFilename)
    splitPointList = makeSplitPointsFromIntervals(silenceIntervalList)
    splitPointList.sort()
    reducedSplitPointList = []
    lastSplitPoint = 0.0
    for sp in splitPointList:
        if sp - lastSplitPoint >= 240.0:
            reducedSplitPointList.append(sp)
            lastSplitPoint = sp
    splitPointList = reducedSplitPointList
    if len(splitPointList) == 0:
        outputFilename = os.path.join(groupDirectoryName, '000.mp3')
        os.rename(concatAudioFilename, outputFilename)
    else:
        outputPattern = os.path.join(groupDirectoryName, "%03d.mp3")
        splitAudio(concatAudioFilename, splitPointList, outputPattern)
        os.remove(concatAudioFilename)
    print(f'done with {groupDirectoryName}')


def step2():
    with open(groupingsFilename, 'r') as groupingsFile:
        directoryIndex = -1
        groupDirectoryName = None
        groupFileList = []
        for line in groupingsFile:
            strippedLine = line.strip()
            if len(strippedLine) == 0 or strippedLine.startswith('#'):
                continue
            if not strippedLine.endswith('.mp3'):
                if len(groupFileList) > 0:
                    groupAndSplitEvenly(groupFileList, groupDirectoryName)
                    for inp in groupFileList:
                        os.remove(inp)
                    groupFileList = []
                directoryIndex += 1
                groupDirectoryName = f'{directoryIndex:02}_{strippedLine}'
                groupDirectoryName = os.path.normpath(groupDirectoryName)
                os.mkdir(groupDirectoryName)
            else:
                if groupDirectoryName is None:
                    directoryIndex = 0
                    groupDirectoryName = os.path.normpath('00')
                    os.mkdir(groupDirectoryName)
                groupFileList.append(strippedLine)
        
        if len(groupFileList) > 0:
            groupAndSplitEvenly(groupFileList, groupDirectoryName)
            for inp in groupFileList:
                os.remove(inp)
            groupFileList = []

def createStep2InstructionsFile():
    with open(step2InstructionsFilename, 'w') as instructionsFile:
        instructions = [
            f'To start step 2, create a file named {groupingsFilename} with the names of all of the mp3 files in this directory. ($ ls *.mp3 > {groupingsFilename})',
            f'Edit this file by inserting chapter names wherever you want a new chapter to start. For example:',
            '',
            '# groupings.txt',
            'prologue',
            '00.mp3',
            '01.mp3',
            '',
            'chap1',
            '02.mp3',
            '03.mp3',
            '04.mp3',
            '05.mp3',
            '',
            'chap2',
            '06.mp3',
            '07.mp3',
            '... and so on'
            '',
            'Then just run the command again in this directory.'
        ]

        for line in instructions:
            print(line, file=instructionsFile)

def createProcessCompleteFile():
    with open(processCompleteFilename, 'w') as f:
        print('delete this file to restart process', file=f)

def main():
    if os.path.exists(processCompleteFilename):
        print(f'Process is complete. To start over, delete {processCompleteFilename}')
    else:
        if not os.path.exists(groupingsFilename):
            if os.path.exists(step2InstructionsFilename):
                print(f'read {step2InstructionsFilename}, or delete it to start over')
            else:
                step1()
                createStep2InstructionsFile()
        else:
            step2()
            createProcessCompleteFile()
            os.remove(groupingsFilename)
            os.remove(step2InstructionsFilename)

if __name__ == '__main__':
    main()

