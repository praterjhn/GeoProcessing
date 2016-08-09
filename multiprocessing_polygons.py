# Author: John Prater praterjhn@gmail.com
# updated: 4/6/16

import arcpy
import os
import sys
import numpy
import scipy
from scipy import interpolate
import multiprocessing
import datetime

arcpy.Delete_management("in_memory")
arcpy.env.overwriteOutput = True

POLYS = arcpy.GetParameterAsText(0) #Feature layer
CLIP_SHP = arcpy.GetParameterAsText(1) #Feature Layer
OUT_FOLDER = arcpy.GetParameterAsText(2) # fodler
CIRCUIT = arcpy.GetParameterAsText(3) #Circuit Name
COORD = arcpy.GetParameterAsText(4) #Coordinate system


def SmoothPolys(BuffPolyCoords):
    
    # to ensure a smooth start/end of the smoothed polygon, need to copy first 
    # few coord pairs (after initial) to end of list
    pair1 = BuffPolyCoords[1]
    pair2 = BuffPolyCoords[2]
    pair3 = BuffPolyCoords[3]

    BuffPolyCoords.append(pair1)
    BuffPolyCoords.append(pair2)
    BuffPolyCoords.append(pair3)

    # divide the list of XY pairs into separate list of X and Y
    Xlist, Ylist = zip(*BuffPolyCoords)

    # convert those lists to arrays
    x = numpy.array(Xlist)
    y = numpy.array(Ylist)

    ''' here is the smoothing routine - using a b-spline that passes through each original polygon vertex
        the interpolate function will make a poly with at least 500 vertices (less results in jagged edges, 
        while more just slows process WAAAAY down without much improvement)'''
    
    # this is necessary to prepare the data for the spline 
    # (smoothing is zero and k=2 is best smoothing polynomial (k3 would be cubic and is too much))
    tck, u = scipy.interpolate.splprep([x,y],s=0.0,k=2) 
    #this performs the spline, it makes a new smoothed polygon with at least 500 vertices
    x2, y2 = scipy.interpolate.splev(numpy.linspace(0,1,250),tck)  

    # now we have the x2 and y2 so we zip the arrays together to create coordinate pairs
    SmoothedCoords = list(zip(x2,y2))

    # get the nearest 3 points to the pair3 coordinate - 
    #these will be candidates to stop removing points of the initial 3 segments
    KDT_pts = scipy.spatial.cKDTree(numpy.array(SmoothedCoords))

    # Find the nearest 2 points to the pair3 and get those values for comparison while deleting first segs in list
    nearQuery = KDT_pts.query((pair3[0],pair3[1]),k=2)
    
    # this is the index of the points nearest pair3
    WatchIndices = nearQuery[1] 

    minimumIndex = min(WatchIndices)
    
    # this is going to delete all index pairs from 0 to specified watch point
    del SmoothedCoords[0:minimumIndex] 
    
    # polygon boundary coordinates - can be used to make a new geometry and add to shapefile output
    return SmoothedCoords 
    
    
def MakePolys(job):
    
    # get unique feature name
    path = os.path.dirname(job)
    name = os.path.basename(job).strip('.shp') + "_SMOOTHED"
    lyr_name = os.path.basename(job).strip('.shp')
    
    # make feature layer in mem
    arcpy.MakeFeatureLayer_management(job, lyr_name)
    
    # create smooth polygons feature class
    COORD = arcpy.Describe(job).spatialReference
    POLYS_SMOOTH = os.path.join("in_memory", name)
    arcpy.CreateFeatureclass_management("in_memory", name, "POLYGON", "", "", "", COORD)
    icurs = arcpy.da.InsertCursor(POLYS_SMOOTH, ["Shape@", "OID"])
    for field in arcpy.ListFields(POLYS_SMOOTH):
        print field.name
        
    with arcpy.da.SearchCursor(lyr_name, ["Shape@"]) as cursor:
        for i, row in enumerate(cursor):
            poly = row[0]
            for array in poly:
                BuffPolyCoords = [] # BuffPolyCoords are the polygon boundary coordinates ((x1,y1),(x2,y,)(x3,y3)....)
                for pnt in array:
                    if pnt is not None:
                        x = pnt.X
                        y = pnt.Y
                        BuffPolyCoords.append((x,y))
                newPolyCoords = SmoothPolys(BuffPolyCoords) # call smoothing routine
                # create arcpy geometry for new polygon
                newPoly = arcpy.Polygon(arcpy.Array(arcpy.Point(item[0], item[1]) for item in newPolyCoords)) 
                icurs.insertRow((newPoly, i)) # insert geometry into feature class
    del icurs    
    SMOOTHED_POLYS = os.path.join(OUT_FOLDER, name + ".shp")
    arcpy.CopyFeatures_management(POLYS_SMOOTH, SMOOTHED_POLYS)
    #return POLYS_SMOOTH
    return SMOOTHED_POLYS


def ParsePolys(polys, cpus, FC_per_cpu):
    
    name = os.path.basename(polys).strip('.shp')
    # PARSE POLYGONS INTO EQUAL(ish) layers FOR MULTIPROCESSING (must be on disk)?
    jobs_list = []
    for i, cpu in enumerate(range(cpus)):
        # feature layer name
        job_name = name + "_job_" + str(cpu) + ".lyr"
        
        # disk path
        job = os.path.join(OUT_FOLDER, job_name.replace('.lyr', '.shp'))
        print job_name
        
        if i == 0:
            # job1
            rangeI = FC_per_cpu
            print "0 - " + str(rangeI)
            arcpy.MakeFeatureLayer_management(polys, job_name, ' "FID" <= ' + str(rangeI))
            arcpy.CopyFeatures_management(job_name, job)
            lyr_count = int(arcpy.GetCount_management(job).getOutput(0))
            #print job + ": " + str(lyr_count)
            #print os.path.abspath(job)
            jobs_list.append(job)
        else:
            # jobN...
            rangeJ = rangeI + FC_per_cpu
            print str(rangeI) + " - " + str(rangeJ)
            arcpy.MakeFeatureLayer_management(polys, job_name, ' "FID" > ' + str(rangeI) + ' AND "FID" <= ' + str(rangeJ))
            arcpy.CopyFeatures_management(job_name, job)
            lyr_count = int(arcpy.GetCount_management(job).getOutput(0))
            #print job + ": " + str(lyr_count)
            #print os.path.abspath(job)
            jobs_list.append(job)
            rangeI = rangeJ
            #print rangeI
            rangeJ += FC_per_cpu
            #print rangeJ
            
    print "\n"
    return jobs_list


def main():
    print str(datetime.datetime.now())
    # NEW 1-27-16: adding a repair geometry step to fix polys from microstation.  
    # Must delete those with null value or else ends up dropping polygons in the final result.
    arcpy.AddMessage("\nChecking/Repairing possible topology errors...")
    REPAIRED = os.path.join("in_memory", "POLYS_Repaired")
    arcpy.CopyFeatures_management(POLYS, REPAIRED) # make copy of original
    arcpy.RepairGeometry_management(REPAIRED, "DELETE_NULL") 
    
    # prep polys for smoothing
    arcpy.AddMessage("Dissolving PRE IVM Polys by 'HANDLE' with no 'Multifeatures'...")
    POLYS_DISS = os.path.join("in_memory", "POLYS_Dissolve")
    arcpy.Dissolve_management(REPAIRED, POLYS_DISS, "HANDLE", "", "SINGLE_PART") 
    
    # get count of polygons
    FC_Count = int(arcpy.GetCount_management(POLYS_DISS).getOutput(0))
    print "\nFC_Count: " + str(FC_Count)
    
    # get number of cpus in machine
    max_cpus = multiprocessing.cpu_count()
    cpus = int(multiprocessing.cpu_count()-1) # let's not be greedy
    print "cpus: " + str(cpus)
    
    # get count of polys per cpu
    total = (FC_Count/cpus) 
    print "FC_Count/cpus: " + str(total)
    
    # account for possible odd number
    remainder = FC_Count%cpus
    FC_per_cpu = total+remainder # always make them non float and make sure we dont leave any out
    print "remainder: " + str(remainder)
    print "FC_per_cpu: " + str(FC_per_cpu) + "\n"
    
    # parse polys for multiprocessing
    arcpy.AddMessage("Parsing PRE IVM Polys...")
    parsed_polys = ParsePolys(POLYS_DISS, cpus, FC_per_cpu)
    
    # BEGIN SMOOTHING 
    arcpy.AddMessage("Smoothing " + str(FC_Count) + " Polygons with " + str(cpus) + " of " + str(max_cpus) + 
                     " cores... hold on to your butts")
    arcpy.AddMessage("\tStarted: " + str(datetime.datetime.now()))

    # CREATE A POOL CLASS AND RUN THE JOBS
    pool = multiprocessing.Pool(processes=cpus)
    smoothed_polys = pool.map(MakePolys, parsed_polys)
    pool.close()
    pool.join()
    
    arcpy.AddMessage("\tFinished: " + str(datetime.datetime.now()))

    # merge pooled polys back together
    POLYS_SMOOTH = os.path.join(OUT_FOLDER, "ALL_Smoothed_Polys.shp")
    arcpy.Merge_management(smoothed_polys, POLYS_SMOOTH)

    # CLEANUP
    for shp in smoothed_polys:
        arcpy.Delete_management(shp)
    
    for shp in parsed_polys:
        arcpy.Delete_management(shp)    

    arcpy.Delete_management("in_memory")
    
    # dissolve
    arcpy.AddMessage("Dissolving smoothed polys...")
    SMOOTH_DISS =  os.path.join("in_memory", "ALL_smoothed_diss")
    arcpy.Dissolve_management(POLYS_SMOOTH, SMOOTH_DISS, "", "", "SINGLE_PART")
    
    # Buffer the smoothed polys by 3 inches to make sure all veg points are enclosed:
    arcpy.AddMessage("Buffering polygons by .25ft...")
    SMOOTH_BUFF = os.path.join(OUT_FOLDER, "ALL_IVM_POLYS.shp")
    arcpy.Buffer_analysis(SMOOTH_DISS, SMOOTH_BUFF, "0.25 FEET")
    
    # import ETGeo tool to perform erase
    arcpy.ImportToolbox("C:\Program Files (x86)\ET SpatialTechniques\ET GeoWizards 11.0 Concurrent for ArcGIS 10.2\ET GeoWizards.tbx")
    FINAL_SHP = os.path.join(OUT_FOLDER, CIRCUIT + "_FINAL_STEP1_IVM_POLYGONS.shp")
    arcpy.AddMessage("Erasing veg polygon overlays from IVM candidates with ETGeoWizard's 'AdvancedMerge' tool...")
    arcpy.gp.ET_GPAdvancedMerge(SMOOTH_BUFF, CLIP_SHP, FINAL_SHP, "Erase")
   
    arcpy.AddMessage("Done with ETGeoWizard...")
    arcpy.AddMessage("Calculating area...")
    
    # ID info
    arcpy.AddField_management(FINAL_SHP, "IVM_ID", "LONG")
    count = 1
    with arcpy.da.UpdateCursor(FINAL_SHP, ["IVM_ID"]) as cursor:
        for row in cursor:
            row[0] = count
            count += 1
            cursor.updateRow(row)
    
    # Add new field (AREA_SQFT) 
    arcpy.AddField_management(FINAL_SHP, "AREA_SQFT", "DOUBLE")
    
    arcpy.AddMessage("Removing polys with less than 4356 sqft (1/10 acre)...")
    # update new field and remove polys less than 4356 ft^2
    count = 0
    with arcpy.da.UpdateCursor(FINAL_SHP, ["Shape@", "AREA_SQFT"]) as cursor:
        for row in cursor:
            poly = row[0]
            area = poly.getArea("GEODESIC", "SQUAREFEET")
            if area <= 4356:
                count += 1
                cursor.deleteRow()
            else:
                row[1] = area
                cursor.updateRow(row)
    arcpy.AddMessage("\t" + str(count) + " polys removed!")
    
    # Delete shapes with duplicate geometry: (added 2-11-16)
    TrackGeometries = []
    with arcpy.da.UpdateCursor(FINAL_SHP, ["SHAPE@XY"]) as cursor:
        for row in cursor:
            if row[0] not in TrackGeometries:
                TrackGeometries.append(row[0])
            else:
                cursor.deleteRow()
    
    arcpy.Delete_management("in_memory")
    arcpy.AddMessage("Final output: " + str(os.path.abspath(FINAL_SHP)))
    arcpy.AddMessage("Done!\n")
    print str(datetime.datetime.now())

if __name__ == '__main__':
    main()


