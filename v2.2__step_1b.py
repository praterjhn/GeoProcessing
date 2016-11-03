# Author: John Prater jprater@quantumspatial.com
# produces a shapefile of the "difference" between 'POLYS_SHP' and 'ERASE_SHP'
# substitute for ESRI "Erase" function which requires ArcEditor/Standard license or better

import os
import shapefile
import time
import arcpy
from shapely.geometry import Polygon, MultiPolygon

arcpy.Delete_management("in_memory")
arcpy.env.overwriteOutput = True

#POLYS_SHP = r"C:\JPRATER\PGE_VM_TROW\SampleData\IGNACIO_SAMPLE\output\Test_1_ALL_POLYS_SMOOTHED.shp"
#ERASE_SHP = r"C:\JPRATER\PGE_VM_TROW\SampleData\IGNACIO_SAMPLE\output\IGNACIO_SAN_RAFAEL_1_TreePolys.shp"
##ERASE_SHP = r"C:\JPRATER\PGE_VM_TROW\SampleData\IGNACIO_SAMPLE\02_VEG_SEG\IGNACIO_SAN_RAFAEL_1_CASP3_VEG_SEG_151105.gdb\IGNACIO_SAN_RAFAEL_1_TreePolys"
#OUT_SHP = "SHAPELY_TEST_4"
#OUT_FOLDER = r"C:\JPRATER\PGE_VM_TROW\SampleData\IGNACIO_SAMPLE\output"

POLYS_SHP = arcpy.GetParameterAsText(0) # feature layer
ERASE_SHP = arcpy.GetParameterAsText(1) # feature layer
OUT_SHP = arcpy.GetParameterAsText(2) # string
OUT_FOLDER = arcpy.GetParameterAsText(3) # folder


def ConvertPolys(polys):
    """ If the shape record has multiple parts (e.g. Polygon with holes) the 'parts' attribute contains
    the index of the first point of each part. If there is only one part then a list containing 0 is returned.
    The first part is the exterior ring: points[i:((i+1)-1)]. All other parts are interior rings.
    The last part should include up to the last point (not -1)."""
    
    polys_list = []
    for poly in polys.iterShapes():
        #ttl_poly_points = len(poly.points)
        poly_parts = poly.parts
        interiors = []
        if len(poly_parts) > 1:
            #arcpy.AddMessage poly_parts
            for i, part in enumerate(poly_parts):
                if i == 0:
                    end_pnt = (poly_parts[i+1])-1
                    #arcpy.AddMessage("Exterior: " + str(part) + "-" + str(end_pnt))
                    exterior = poly.points[:end_pnt]
                if i > 0 and i != len(poly_parts)-1:
                    end_pnt = (poly_parts[i+1])-1
                    #arcpy.AddMessage("Interior: " + str(part) + "-" + str(end_pnt))
                    interior = poly.points[part:end_pnt]
                    inner_ring = Polygon(interior)
                    interiors.append(interior)
                if i == len(poly_parts)-1:
                    #arcpy.AddMessage("Interior: " + str(part) + "-" + str(ttl_poly_points))
                    interior = poly.points[part:]
                    interiors.append(interior)                    
            poly_shp = Polygon(exterior, interiors).buffer(0)
            # debugging
            x = poly_shp.geom_type
            poly_shp_wkt = poly_shp.wkt
            poly_shp_vld = poly_shp.is_valid
            moo=5
        else:
            poly_shp = Polygon(poly.points).buffer(0)
            # debugging
            x = poly_shp.geom_type
            poly_shp_wkt = poly_shp.wkt
            poly_shp_vld = poly_shp.is_valid
            moo=5
        polys_list.append(poly_shp)
    return polys_list
    

def main():
    global ERASE_SHP
    if not str(ERASE_SHP).endswith('.shp'):
        arcpy.AddMessage("Converting Erase feature class to shapefile...")
        NEW_ERASE_SHP = os.path.join("in_memory", OUT_SHP + "_1")
        arcpy.CopyFeatures_management(ERASE_SHP, NEW_ERASE_SHP)
        ERASE_SHP = NEW_ERASE_SHP
    
    # fix veg polys... there is likely bad geometry (self intersecting rings, overlaping polys, etc.)
    arcpy.AddMessage("Repairing potential invalid geometry with Erase polys...")
    
    ERASE_SHP_UNION = os.path.join("in_memory", OUT_SHP + "_union")
    arcpy.Union_analysis(ERASE_SHP, ERASE_SHP_UNION, "ALL", "1 FEET", "GAPS")
    arcpy.DeleteIdentical_management(ERASE_SHP_UNION, "Shape")
    
#    ERASE_SHP_UNION_DISS = os.path.join(OUT_FOLDER, OUT_SHP + '_union_diss_repair.shp')
    ERASE_SHP_UNION_DISS = os.path.join(OUT_FOLDER, OUT_SHP + '_union_diss_repair.shp')
    arcpy.Dissolve_management(ERASE_SHP_UNION, ERASE_SHP_UNION_DISS, "", "", "SINGLE_PART")
    arcpy.RepairGeometry_management(ERASE_SHP_UNION_DISS, 'DELETE_NULL')
    
    ERASE_SHP = ERASE_SHP_UNION_DISS
    arcpy.AddMessage("Created:\n" + str(ERASE_SHP))
    
    # ESRI -> PYSHP
    arcpy.AddMessage("Reading shapefiles...")
    shpA = shapefile.Reader(POLYS_SHP)
    shpB = shapefile.Reader(ERASE_SHP)
    
    # PYSHP -> SHAPELY
    arcpy.AddMessage("Converting IVM Polygons...")
    shpA_polys = ConvertPolys(shpA)    
    shpA_multipolys = MultiPolygon(shpA_polys)
    
    arcpy.AddMessage("Converting Erase Polygons...")
    shpB_polys = ConvertPolys(shpB)
    shpB_multipolys = MultiPolygon(shpB_polys)
    
    # SHAPELY
    arcpy.AddMessage("Performing Erase...")
    arcpy.AddMessage(time.strftime("%H:%M"))
    
    try:
        shpC = shpA_multipolys.difference(shpB_multipolys) # SHAPELY [(x,y),(x,y),...]
    except Exception as error:
        message = error.message
        args = error.args
        raise error
    
    arcpy.AddMessage(time.strftime("%H:%M"))
    
    # SHAPELY -> PYSHP
    FINAL_SHP = os.path.join(OUT_FOLDER, OUT_SHP + ".shp")
    
    arcpy.AddMessage("Saving: " + os.path.basename(FINAL_SHP))
    
    w = shapefile.Writer(shapefile.POLYGON)
    w.field('ID')   
    
    for i, geom in enumerate(list(shpC.geoms)):
        shpC_exterior = []
        shpC_pyshp_fmt = []
        # get exterior rings
        for coord in geom.exterior.coords:
            x_y = [coord[0], coord[1]] # PYSHP [[[x,y],[x,y],...]]
            shpC_exterior.append(x_y)
        shpC_pyshp_fmt.append(shpC_exterior)
        # get interior rings
        if len(list(geom.interiors)) > 0:
            for i, ring in enumerate(list(geom.interiors)):
                shpC_interior = []
                for coord in list(ring.coords):
                    x_y = [coord[0], coord[1]]
                    shpC_interior.append(x_y)
                ##check sign, counter clockwise point order creates hole, else overlapping poly
                #if shapefile.signed_area(list(ring.coords)) >= 0:
                    #shpC_interior.reverse()
                shpC_pyshp_fmt.append(shpC_interior)
        
        w.poly(shpC_pyshp_fmt)
        w.record(ID='0')
    
    w.save(FINAL_SHP)

    arcpy.AddMessage("Done!")

if __name__ == '__main__':
    main()