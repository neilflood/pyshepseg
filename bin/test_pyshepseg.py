#!/usr/bin/env python

#Copyright 2021 Neil Flood and Sam Gillingham. All rights reserved.
#
#Permission is hereby granted, free of charge, to any person 
#obtaining a copy of this software and associated documentation 
#files (the "Software"), to deal in the Software without restriction, 
#including without limitation the rights to use, copy, modify, 
#merge, publish, distribute, sublicense, and/or sell copies of the 
#Software, and to permit persons to whom the Software is furnished 
#to do so, subject to the following conditions:
#
#The above copyright notice and this permission notice shall be 
#included in all copies or substantial portions of the Software.
#
#THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, 
#EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES 
#OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. 
#IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR 
#ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF 
#CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION 
#WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from __future__ import print_function, division

import os
import argparse
import time

import numpy
from osgeo import gdal

from pyshepseg import shepseg

def getCmdargs():
    p = argparse.ArgumentParser()
    p.add_argument("-i", "--infile", 
        default="l8olre_p090r079_m201909201911_dbim6.img",
        help="Input Landsat file (default=%(default)s)")
    p.add_argument("-o", "--outfile")
    p.add_argument("-n", "--nclusters", default=30, type=int,
        help="Number of clusters (default=%(default)s)")
    p.add_argument("--subsamplepcnt", type=int, default=1,
        help="Percentage to subsample for fitting (default=%(default)s)")
    p.add_argument("--fourway", default=False, action="store_true",
        help="Use 4-way instead of 8-way")
    cmdargs = p.parse_args()
    return cmdargs


def main():
    cmdargs = getCmdargs()
    
    t0 = time.time()
    print("Reading ... ", end='')
    ds = gdal.Open(cmdargs.infile)
    bandList = []
    imgNullVal_normed = 100
    for bn in [3, 4, 5]:
        b = ds.GetRasterBand(bn)
        refNull = b.GetNoDataValue()
        a = b.ReadAsArray()
        bandList.append(a)
    img = numpy.array(bandList)
    
    del bandList
    print(round(time.time()-t0, 1), "seconds")
    
    seg = shepseg.doShepherdSegmentation(img, 
        numClusters=60, clusterSubsamplePcnt=0.5,
        minSegmentSize=100, maxSpectralDiff=100000, imgNullVal=refNull,
        fourConnected=cmdargs.fourway, verbose=True)
        
    segSize = shepseg.makeSegSize(seg)
    maxSegId = seg.max()
    spectSum = shepseg.buildSegmentSpectra(seg, img, maxSegId)

    # Write output    
    outType = gdal.GDT_UInt32
    
    (nRows, nCols) = seg.shape
    outDrvr = ds.GetDriver()
    outDrvr = gdal.GetDriverByName('KEA')
    if os.path.exists(cmdargs.outfile):
        outDrvr.Delete(cmdargs.outfile)
    outDs = outDrvr.Create(cmdargs.outfile, nCols, nRows, 1, outType)
        #options=['COMPRESS=YES'])
    outDs.SetProjection(ds.GetProjection())
    outDs.SetGeoTransform(ds.GetGeoTransform())
    b = outDs.GetRasterBand(1)
    b.WriteArray(seg)
    b.SetMetadataItem('LAYER_TYPE', 'thematic')
    b.SetNoDataValue(shepseg.SEGNULLVAL)
    setColourTable(b, segSize, spectSum)
    del outDs


def setColourTable(bandObj, segSize, spectSum):
    """
    Set a colour table based on the segment mean spectral values. 
    It assumes we only used three bands, and assumes they will be
    mapped to (blue, green, red) in that order. 
    """
    nRows, nBands = spectSum.shape

    attrTbl = bandObj.GetDefaultRAT()
    attrTbl.SetRowCount(nRows)
    
    colNames = ["Blue", "Green", "Red"]
    colUsages = [gdal.GFU_Blue, gdal.GFU_Green, gdal.GFU_Red]
    
    for band in range(nBands):
        meanVals = spectSum[..., band] / segSize
        minVal = meanVals[1:].min()
        maxVal = meanVals[1:].max()
        colour = 255 * ((meanVals - minVal) / (maxVal - minVal))
        
        attrTbl.CreateColumn(colNames[band], gdal.GFT_Integer, colUsages[band])
        colNum = attrTbl.GetColumnCount() - 1
        attrTbl.WriteArray(colour.astype(numpy.uint), colNum)
        
    # alpha
    alpha = numpy.full((nRows,), 255, dtype=numpy.uint8)
    attrTbl.CreateColumn('Alpha', gdal.GFT_Integer, gdal.GFU_Alpha)
    colNum = attrTbl.GetColumnCount() - 1
    attrTbl.WriteArray(alpha, colNum)
    
    # histo
    attrTbl.CreateColumn('Histogram', gdal.GFT_Integer, gdal.GFU_PixelCount)
    colNum = attrTbl.GetColumnCount() - 1
    attrTbl.WriteArray(segSize, colNum)
    
    
if __name__ == "__main__":
    main()