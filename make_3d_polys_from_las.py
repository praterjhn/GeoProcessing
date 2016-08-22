# 6/02/2015
# john_prater()

import arcpy
import os
import sys
import traceback
import numpy as np
import Stats as Sts
from scipy.spatial import KDTree
from scipy.spatial import distance
from laspy.file import File

#POLYS_2D       = "C:\\JPRATER\\2D_3D Buildings\\3D_Buildings_Z_Attribution\\RAW_BUILDINGS_IDs.shp"
#BUILDING_LAS   = "C:\\JPRATER\\2D_3D Buildings\\3D_Buildings_Z_Attribution\\las\\SanLuis_61_buildings.las"
#outFolder      = "C:\\JPRATER\\2D_3D Buildings\\3D_Buildings_Z_Attribution\\output"

POLYS_2D     = arcpy.GetParameterAsText(0)
BUILDING_LAS = arcpy.GetParameterAsText(1)
outFolder    = arcpy.GetParameterAsText(2)

arcpy.env.workspace = outFolder
arcpy.env.overwriteOutput = True
arcpy.Delete_management('in_memory')

def Query2DLasTree(Pnt):
    result = tree2D.query_ball_point(Pnt, .5)
    if len(result) == 0:
        # if ball query returns nothing use regular query to 
        # find nearest points and use their avg Z            
        result = tree2D.query(Pnt, 6)
        result_z_lst = [round(lasArray3D[i][2],2) for i in result[1]]
        result_z_lst.sort()
        result_z_med = Sts.median(result_z_lst)
        result_z_max = max(result_z_lst)
        result_z_min = min(result_z_lst)
        result_z_range = result_z_max - result_z_min 
    else:
        # if ball query returns points use their median Z
        result_z_lst = [round(lasArray3D[i][2],2) for i in result]
        result_z_lst.sort()
        result_z_med = Sts.median(result_z_lst)
        result_z_max = max(result_z_lst)
        result_z_min = min(result_z_lst)
        result_z_range = result_z_max - result_z_min
        
    return [result_z_min, result_z_max, result_z_med, result_z_range, result_z_lst]

try:
    arcpy.CheckOutExtension('3D')
    arcpy.CheckOutExtension("Spatial")
    
    sr = arcpy.Describe(POLYS_2D).spatialReference
    
    '''make las dataset and compute raster of z_ranges'''
    # create lasd and raster and stats 
    LASD = os.path.join(outFolder, "lasd.lasd")
    arcpy.CreateLasDataset_management(BUILDING_LAS, LASD, "", "", sr, "COMPUTE_STATS")
    LASD_rstr = os.path.join(outFolder, "lasd_rstr.img")
    arcpy.LasDatasetToRaster_conversion(LASD, LASD_rstr, "ELEVATION", "BINNING AVERAGE LINEAR", "FLOAT", "CELLSIZE", "0.7", "1")    

    '''get list of vertices from input polys'''
    # create list of roof polygon points
    arcpy.AddMessage("Getting list of 2D roof vertices...")
    roofPnts = []
    feaNum = 0
    for row in arcpy.da.SearchCursor(POLYS_2D, ["SHAPE@", "BLDG_ID"]):
        # Step into the array of the polygon
        for array in row[0]:
            # Step through each point in the array
            for Pnt in array:
                x = Pnt.X
                y = Pnt.Y
                z = 0.0
                ID = row[1]
                # build list of vertices
                roofPnts.append([x,y,z,feaNum,ID])
            feaNum += 1 # next line part
    del row
    
    '''setup numpy arrays and KDTrees of input las'''
    # read las and make np array of points
    arcpy.AddMessage("Creating numpy array and KDTrees of LAS...")
    inFile = File(BUILDING_LAS, mode = "r")
    lasArray3D = np.vstack([inFile.x, inFile.y, inFile.z]).transpose()
    lasArray2D = np.vstack([inFile.x, inFile.y]).transpose()
        
    # build kd tree2D with lidar
    tree2D = KDTree(lasArray2D)
    tree3D = KDTree(lasArray3D)
    
    ''' make initial z assignments '''
    ''' METHOD: set Pnt.Z to highest z first, then if incorrect, iteratively determine next best low z '''
    arcpy.AddMessage("Sampling LAS trees...")
    for Pnt in roofPnts:
        result = Query2DLasTree(Pnt[:2])
        z_range = result[3]
        if z_range > 1.0:
            Pnt[2] = result[1] # max
        else:      
            Pnt[2] = result[2] # med      
    
    ''' create shapefile of 3D enabled polygons '''
    # create 3D polygon
    arcpy.AddMessage("Creating 3D Buildings...")
    
    Polys3D = os.path.join(outFolder, "Roof_Polys_3D.shp")
    PolyPnts3D = os.path.join(outFolder, "Roof_Poly_Points_3D.shp")
    if arcpy.Exists(Polys3D):
        arcpy.Delete_management(Polys3D)
    if arcpy.Exists(PolyPnts3D):
        arcpy.Delete_management(PolyPnts3D)
    arcpy.CreateFeatureclass_management(outFolder, "Roof_Polys_3D.shp", "POLYGON", "", "ENABLED", "ENABLED", sr)
    arcpy.AddField_management(Polys3D, "BLDG_ID", "LONG")
    
    icurs1 = arcpy.da.InsertCursor(Polys3D, ["SHAPE@", "BLDG_ID"])       
    ID = 0
    roofPart3D = []
    for Pnt in roofPnts:
        # build list of points that makeup the poly
        if ID == Pnt[3]:
            roofVertex = arcpy.Point(Pnt[0], Pnt[1], Pnt[2])
            roofPart3D.append(roofVertex)
            BLDG_ID = Pnt[4]
        # make poly geometry and insert into shapefile
        if ID != Pnt[3]:
            polygon = arcpy.Polygon(arcpy.Array(roofPart3D), sr, True, True)
            icurs1.insertRow((polygon, BLDG_ID))
            ID += 1
            roofPart3D = []    
    del icurs1
    
    ''' check for geometry error '''
    # do stuff to check for quality
    arcpy.AddMessage("Checking for geometry problems...")
    
    geom_table = os.path.join("in_memory", "geom_tbl")
    arcpy.CheckGeometry_management(Polys3D, geom_table)
    count = int(arcpy.GetCount_management(geom_table).getOutput(0))
    
    if count > 0:
        arcpy.AddWarning("Found " + str(count) + " geometry issues! Check output table.")
        arcpy.JoinField_management(Polys3D, "FID", geom_table, "FEATURE_ID")
    else:
        arcpy.AddMessage("    No geometry problems found!")
    
    ''' add polygon geometry attributes to the polygon shapefile '''
    # add slope values to each roof plane (avg slope is % grade)
    arcpy.AddMessage("Calculating roof slopes...")    
    
    ######### need to substitute this with custom gradient/slope calculation code #############
    arcpy.AddZInformation_3d(Polys3D, ["AVG_SLOPE", "MAX_SLOPE"])
    #####################################################################################
    
    ''' add input las raster attributes to the polygon shapefile '''
    arcpy.AddMessage("Correcting bad roof planes...")
    LASD_tbl = os.path.join(outFolder, "lasd_tbl.dbf")
    arcpy.gp.ZonalStatisticsAsTable_sa(Polys3D, "FID", LASD_rstr, LASD_tbl, "NODATA", "ALL")
    # add fields ["FID_", "COUNT", "AREA", "MIN", "MAX", "RANGE", "MEAN", "STD", "SUM"]
    arcpy.JoinField_management(Polys3D, "FID", LASD_tbl, "FID_")
    
    ''' if slope is steep, determine next best vertex elevation by analyzing average elevations of las inside polygon '''
    arcpy.MakeFeatureLayer_management(Polys3D, "polys3d_lyr")
    arcpy.SelectLayerByAttribute_management("polys3d_lyr", "NEW_SELECTION", '"MAX_SLOPE" > 58.0')
    count = int(arcpy.GetCount_management("polys3d_lyr").getOutput(0))
    
    terminator = 0
    while count != 0:
        if terminator == 20:
            break
        with arcpy.da.UpdateCursor(Polys3D, ["SHAPE@", "Max_Slope", "MEAN", "AREA"]) as cursor:
            for row in cursor:
                if row[1] > 58.0:#if polygon has a very steep point/part
                    for array in row[0]:
                        poly_z_lst = [Pnt.Z for Pnt in array] # make list of point geometry z's
                        poly_z_min = min(poly_z_lst) # get min z
                        poly_z_max = max(poly_z_lst) # get max z
                        poly_z_avg = sum(poly_z_lst)/len(poly_z_lst)
                        roofPart3D = []
                        for Pnt in array:
                            XY = (Pnt.X, Pnt.Y)
                            result = Query2DLasTree(XY)
                            result_z_lst = result[4]
                            result_z_range = result[3]
                            result_z_med = result[2]
                            result_z_max = result[1]
                            result_z_min = result[0]   
                            
                            if terminator == 0 and row[3] < 10 and Pnt.Z > row[2]:
                                Pnt.Z = row[2]
                                                
                            if Pnt.Z == poly_z_max:
                                if result_z_range > 1.0:
                                    lst_query = min(enumerate(result_z_lst), key=lambda x: abs(x[1]-Pnt.Z))
                                    if lst_query[0] != 0:
                                        next_z = lst_query[0] - 1
                                        Pnt.Z = result_z_lst[next_z]
                                    else:
                                        Pnt.Z = row[2]
                            if Pnt.Z == poly_z_min:
                                if result_z_range > 1.0:
                                    lst_query = min(enumerate(result_z_lst), key=lambda x: abs(x[1]-Pnt.Z))
                                    if lst_query[0] != len(result_z_lst)-1:
                                        next_z = lst_query[0] + 1
                                        Pnt.Z = result_z_lst[next_z]
                                    else:
                                        Pnt.Z = row[2]
                                
                            # need to rebuild polygon geometry object
                            roofVertex = arcpy.Point(Pnt.X, Pnt.Y, Pnt.Z)                        
                            roofPart3D.append(roofVertex)
                        polygon = arcpy.Polygon(arcpy.Array(roofPart3D), sr, True, True)
                        row[0] = polygon
                        cursor.updateRow(row)                                
    
        # recalculate polygon geometry                
        arcpy.DeleteField_management(Polys3D, "AVG_SLOPE")
        arcpy.DeleteField_management(Polys3D, "MAX_SLOPE")
        arcpy.AddZInformation_3d(Polys3D, ["AVG_SLOPE", "MAX_SLOPE"])
        
        arcpy.MakeFeatureLayer_management(Polys3D, "polys3d_lyr")
        arcpy.SelectLayerByAttribute_management("polys3d_lyr", "NEW_SELECTION", '"MAX_SLOPE" > 58.0')
        count = int(arcpy.GetCount_management("polys3d_lyr").getOutput(0))        

        terminator += 1

    arcpy.MakeFeatureLayer_management(Polys3D, "polys3d_lyr")
    arcpy.SelectLayerByAttribute_management("polys3d_lyr", "NEW_SELECTION", '"MAX_SLOPE" > 58.0')
    count = int(arcpy.GetCount_management("polys3d_lyr").getOutput(0))    
    terminator = 0
    while count != 0:
        if terminator == 20:
            break
        with arcpy.da.UpdateCursor(Polys3D, ["SHAPE@", "Max_Slope", "MEAN"]) as cursor:
            for row in cursor:
                if row[1] > 30.0:#if polygon has a very steep point/part
                    for array in row[0]:
                        poly_z_lst = [Pnt.Z for Pnt in array] # make list of point geometry z's
                        poly_z_min = min(poly_z_lst) # get min z
                        poly_z_max = max(poly_z_lst) # get max z
                        poly_z_avg = sum(poly_z_lst)/len(poly_z_lst)
                        roofPart3D = []
                        for Pnt in array:
                            XY = (Pnt.X, Pnt.Y)
                            result = Query2DLasTree(XY)
                            result_z_lst = result[4]
                            result_z_range = result[3]
                            result_z_med = result[2]
                            result_z_max = result[1]
                            result_z_min = result[0] 
                                                
                            if Pnt.Z == poly_z_max:
                                if result_z_range > 1.0:
                                    lst_query = min(enumerate(result_z_lst), key=lambda x: abs(x[1]-Pnt.Z))
                                    if lst_query[0] != 0:
                                        next_z = lst_query[0] - 1
                                        if result_z_lst[next_z] < poly_z_min:
                                            pass
                                        else:
                                            Pnt.Z = result_z_lst[next_z]
                                    else:
                                        Pnt.Z = row[2]
                                
                            # need to rebuild polygon geometry object
                            roofVertex = arcpy.Point(Pnt.X, Pnt.Y, Pnt.Z)                        
                            roofPart3D.append(roofVertex)
                        polygon = arcpy.Polygon(arcpy.Array(roofPart3D), sr, True, True)
                        row[0] = polygon
                        cursor.updateRow(row)                                
    
        # recalculate polygon geometry                
        arcpy.DeleteField_management(Polys3D, "AVG_SLOPE")
        arcpy.DeleteField_management(Polys3D, "MAX_SLOPE")
        arcpy.AddZInformation_3d(Polys3D, ["AVG_SLOPE", "MAX_SLOPE"])
        
        arcpy.MakeFeatureLayer_management(Polys3D, "polys3d_lyr")
        arcpy.SelectLayerByAttribute_management("polys3d_lyr", "NEW_SELECTION", '"MAX_SLOPE" > 58.0')
        count = int(arcpy.GetCount_management("polys3d_lyr").getOutput(0))        

        terminator += 1                                
        
    # recalculate polygon geometry                
    arcpy.DeleteField_management(Polys3D, "AVG_SLOPE")
    arcpy.DeleteField_management(Polys3D, "MAX_SLOPE")
    arcpy.AddZInformation_3d(Polys3D, ["AVG_SLOPE", "MAX_SLOPE"])   
            
    arcpy.AddMessage("Creating polygon vertex shapefile...")
    arcpy.CreateFeatureclass_management(outFolder, "Roof_Poly_Points_3D.shp", "POINT", "", "ENABLED", "ENABLED", sr)
    arcpy.AddField_management(PolyPnts3D, "X", "DOUBLE")
    arcpy.AddField_management(PolyPnts3D, "Y", "DOUBLE")
    arcpy.AddField_management(PolyPnts3D, "Z", "DOUBLE")
    arcpy.AddField_management(PolyPnts3D, "PNT_ID", "SHORT")
    arcpy.AddField_management(PolyPnts3D, "POLY_ID", "SHORT")
    arcpy.AddField_management(PolyPnts3D, "BLDG_ID", "LONG")

    icurs2 = arcpy.da.InsertCursor(PolyPnts3D, ["SHAPE@", "X", "Y", "Z", "PNT_ID", "POLY_ID", "BLDG_ID"])
    
    BLDG_ID = []
    poly_id = 0    
    with arcpy.da.SearchCursor(Polys3D, ["SHAPE@", "BLDG_ID"]) as cursor:
        for row in cursor:
            pnt_id = 0
            if row[1] not in BLDG_ID:
                BLDG_ID.append(row[1])
                poly_id = 0
            else:
                poly_id += 1
            for array in row[0]:
                for Pnt in array:
                    icurs2.insertRow((arcpy.Point(Pnt.X, Pnt.Y, Pnt.Z), Pnt.X, Pnt.Y, Pnt.Z, pnt_id, poly_id, row[1]))
                    pnt_id += 1
    del icurs2
            
    #clean up
    arcpy.DeleteField_management(Polys3D, "Id")
    arcpy.DeleteField_management(PolyPnts3D, "Id")
    #arcpy.Delete_management(LASD)
    #arcpy.Delete_management(LASD_rstr)
    #arcpy.Delete_management(LASD_tbl)
    arcpy.AddMessage("Done!")
    
except Exception as e:
    tb = sys.exc_info()[2]
    tbinfo = traceback.format_tb(tb)[0]   
    arcpy.AddError("\nTraceback info:\n" + tbinfo)
    arcpy.AddError(e.message)
    arcpy.Delete_management('in_memory')
    sys.exit()

