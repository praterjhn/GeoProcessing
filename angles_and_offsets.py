# Author: John Prater praterjhn@gmail.com
# Date: 1/27/2016
# For: Utility Analytics

""" Use the geometry of the tower report to calculate distances from the top
    of a tower to each attachment point on that tower """

import arcpy
import os
from math import *

arcpy.env.overwriteOutput = True

TwrRprt = arcpy.GetParameterAsText(0)  # file - CSV of tower locations
InsLins = arcpy.GetParameterAsText(1)  # layer - Shapefile of insulator lines (dead ends/suspensions)
InsPost = arcpy.GetParameterAsText(2)  # layer - Shapefile of insulator points (posts)
InsShld = arcpy.GetParameterAsText(3)  # layer - Shapefile of insulator shields 
CordSys = arcpy.GetParameterAsText(4)  # coordinate system - ArcGIS style
OutFldr = arcpy.GetParameterAsText(5)  # folder - directory

''' Create attachment points '''

# create arc table of tower report
twrRpt_temp = os.path.join("in_memory", "TwrRpt")
arcpy.TableToTable_conversion(TwrRprt, "in_memory", "TwrRpt")

# create shapefile of tower report
twrRpt_shp = os.path.join(OutFldr, "Tower_Report.shp")
arcpy.CreateFeatureclass_management(OutFldr, "Tower_Report.shp", "POINT", "", "ENABLED", "ENABLED", CordSys)
arcpy.AddField_management(twrRpt_shp, "QSI_Tower", "SHORT")
arcpy.AddField_management(twrRpt_shp, "STRUCTURE", "TEXT")
arcpy.AddField_management(twrRpt_shp, "TWR_X", "DOUBLE")
arcpy.AddField_management(twrRpt_shp, "TWR_Y", "DOUBLE")
arcpy.AddField_management(twrRpt_shp, "TWR_Z1", "DOUBLE")
arcpy.AddField_management(twrRpt_shp, "TWR_Z2", "DOUBLE")
arcpy.AddField_management(twrRpt_shp, "TWR_LAT", "DOUBLE")  # need lat for trig functions later
arcpy.AddField_management(twrRpt_shp, "TWR_LONG", "DOUBLE")  # need long for trig functions later
arcpy.DeleteField_management(twrRpt_shp, "Id")

icurs = arcpy.da.InsertCursor(twrRpt_shp,
                              ["Shape@XY", "Shape@Z", "QSI_Tower", "STRUCTURE", "TWR_X", "TWR_Y", "TWR_Z1", "TWR_Z2",
                               "TWR_LAT", "TWR_LONG"])

with arcpy.da.SearchCursor(twrRpt_temp, ["QSI_Tower", "X", "Y", "Z1", "Z2", "STRUCTURE"]) as cursor:
    for row in cursor:
        qsiTwr = row[0]
        x = row[1]
        y = row[2]
        z1 = row[3]
        z2 = row[4]
        struct = row[5]
        if qsiTwr is not None:
            icurs.insertRow(((x, y), z1, qsiTwr, struct, x, y, z1, z2, 0, 0))
del icurs

# add lat and long in decimal degree
sr = arcpy.SpatialReference(104145)  # GCS_NAD_1983_2011
with arcpy.da.UpdateCursor(twrRpt_shp, ["Shape@XY", "TWR_LAT", "TWR_LONG"], "", sr) as cursor:
    for row in cursor:
        lat = row[0][1]  # Y
        lon = row[0][0]  # X
        row[1] = lat
        row[2] = lon
        cursor.updateRow(row)

# create attachments data
attachments = os.path.join("in_memory", "Attachments")
arcpy.CreateFeatureclass_management("in_memory", "Attachments", "POINT", "", "", "ENABLED", CordSys)
arcpy.AddField_management(attachments, "INS_ID", "LONG")
arcpy.AddField_management(attachments, "INS_664", "SHORT")
arcpy.AddField_management(attachments, "INS_632", "SHORT")
arcpy.AddField_management(attachments, "POST", "SHORT")
arcpy.AddField_management(attachments, "SHIELD", "SHORT")
arcpy.AddField_management(attachments, "LENGTH", "DOUBLE")
arcpy.AddField_management(attachments, "INS_X", "DOUBLE")
arcpy.AddField_management(attachments, "INS_Y", "DOUBLE")
arcpy.AddField_management(attachments, "INS_Z", "DOUBLE")

icurs = arcpy.da.InsertCursor(attachments,
                              ["Shape@XY", "Shape@Z", "INS_ID", "INS_664", "INS_632", "POST", "SHIELD", "LENGTH",
                               "INS_X", "INS_Y", "INS_Z"])

ID = 0
if arcpy.Exists(InsLins):
    # lines must be drawn from wire to tower in microstation
    # if not, the domino effect of fail starts here
    with arcpy.da.SearchCursor(InsLins, ["Shape@"]) as cursor:
        for row in cursor:
            ID += 1
            pnt_664 = row[0].firstPoint  # wire attachment
            pnt_664_X = pnt_664.X
            pnt_664_Y = pnt_664.Y
            pnt_664_Z = pnt_664.Z
            pnt_632 = row[0].lastPoint  # cross arm (tower) attachment
            pnt_632_X = pnt_632.X
            pnt_632_Y = pnt_632.Y
            pnt_632_Z = pnt_632.Z
            length = round(row[0].length3D, 1)
            icurs.insertRow(
                ((pnt_664_X, pnt_664_Y), pnt_664_Z, ID, 1, 0, 0, 0, length, pnt_664_X, pnt_664_Y, pnt_664_Z))
            icurs.insertRow(
                ((pnt_632_X, pnt_632_Y), pnt_632_Z, ID, 0, 1, 0, 0, length, pnt_632_X, pnt_632_Y, pnt_632_Z))

# insert posts and shields into attachment data if they exist
if arcpy.Exists(InsPost):
    with arcpy.da.SearchCursor(InsPost, ["Shape@XY", "Shape@Z"]) as cursor:
        for row in cursor:
            ID += 1
            x = row[0][0]
            y = row[0][1]
            z = row[1]
            icurs.insertRow(((x, y), z, ID, 0, 0, 1, 0, 0.0, x, y, z))

if arcpy.Exists(InsShld):
    with arcpy.da.SearchCursor(InsShld, ["Shape@XY", "Shape@Z"]) as cursor:
        for row in cursor:
            ID += 1
            x = row[0][0]
            y = row[0][1]
            z = row[1]
            icurs.insertRow(((x, y), z, ID, 0, 0, 0, 1, 0.0, x, y, z))
del icurs
del ID

# need to join attachment points to towers
# make field maps for join
fm1 = arcpy.FieldMap()
fm2 = arcpy.FieldMap()
fm3 = arcpy.FieldMap()
fm4 = arcpy.FieldMap()
fm5 = arcpy.FieldMap()
fm6 = arcpy.FieldMap()
fm7 = arcpy.FieldMap()
fm8 = arcpy.FieldMap()
fm9 = arcpy.FieldMap()
fm10 = arcpy.FieldMap()
fm11 = arcpy.FieldMap()
fm12 = arcpy.FieldMap()
fm13 = arcpy.FieldMap()
fm14 = arcpy.FieldMap()
fm15 = arcpy.FieldMap()
fm16 = arcpy.FieldMap()
fm17 = arcpy.FieldMap()
fms = arcpy.FieldMappings()

fm1.addInputField(twrRpt_shp, "QSI_Tower")
fm2.addInputField(twrRpt_shp, "STRUCTURE")
fm3.addInputField(twrRpt_shp, "TWR_X")
fm4.addInputField(twrRpt_shp, "TWR_Y")
fm5.addInputField(twrRpt_shp, "TWR_Z1")
fm6.addInputField(twrRpt_shp, "TWR_Z2")
fm7.addInputField(twrRpt_shp, "TWR_LAT")
fm8.addInputField(twrRpt_shp, "TWR_LONG")
fm9.addInputField(attachments, "INS_ID")
fm10.addInputField(attachments, "INS_664")
fm11.addInputField(attachments, "INS_632")
fm12.addInputField(attachments, "POST")
fm13.addInputField(attachments, "SHIELD")
fm14.addInputField(attachments, "LENGTH")
fm15.addInputField(attachments, "INS_X")
fm16.addInputField(attachments, "INS_Y")
fm17.addInputField(attachments, "INS_Z")

fms.addFieldMap(fm1)
fms.addFieldMap(fm2)
fms.addFieldMap(fm3)
fms.addFieldMap(fm4)
fms.addFieldMap(fm5)
fms.addFieldMap(fm6)
fms.addFieldMap(fm7)
fms.addFieldMap(fm8)
fms.addFieldMap(fm9)
fms.addFieldMap(fm10)
fms.addFieldMap(fm11)
fms.addFieldMap(fm12)
fms.addFieldMap(fm13)
fms.addFieldMap(fm14)
fms.addFieldMap(fm15)
fms.addFieldMap(fm16)
fms.addFieldMap(fm17)

# final output file
atchmts_twrs = os.path.join(OutFldr, "Method_1_Machine_Output.shp")
arcpy.SpatialJoin_analysis(attachments, twrRpt_shp, atchmts_twrs, "JOIN_ONE_TO_ONE", "KEEP_ALL", fms, "CLOSEST")
arcpy.DeleteField_management(atchmts_twrs, ["Join_Count", "Target_FID"])

''' Calculate bearing angles from spans '''

# create spans shapefile for angle calculations
spans = os.path.join(OutFldr, "Spans.shp")
arcpy.CreateFeatureclass_management(OutFldr, "Spans.shp", "POLYLINE", "", "", "", CordSys)
arcpy.AddField_management(spans, "PLS_ANGLE", "DOUBLE")
arcpy.AddField_management(spans, "BEARING", "DOUBLE")
arcpy.AddField_management(spans, "LENGTH", "DOUBLE")

icurs = arcpy.da.InsertCursor(spans, ["Shape@", "Id", "PLS_ANGLE", "BEARING", "LENGTH"])

ID = 0
flag = 0
branches = []  # use this to keep track of spans
with arcpy.da.SearchCursor(twrRpt_shp, ["Shape@XY", "TWR_LAT", "TWR_LONG", "QSI_Tower"]) as cursor:
    for i, row in enumerate(cursor):
        # first tower
        if i == 0:
            # set 1st coordinate variables
            x1 = row[0][0]
            y1 = row[0][1]
            lat1 = radians(float(row[1]))  # Y
            lon1 = radians(float(row[2]))  # X
            pnt_A = arcpy.Point(x1, y1)

        # second tower
        elif i == 1:
            # set 2nd coordinate variables
            ID += 1
            x2 = row[0][0]
            y2 = row[0][1]
            lat2 = radians(float(row[1]))  # Y
            lon2 = radians(float(row[2]))  # X
            pnt_B = arcpy.Point(x2, y2)

            # calculate span bearing angle
            # calculates an angle clockwise from true north
            bearing = atan2(sin(lon2 - lon1) * cos(lat2),
                            cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(lon2 - lon1))
            bearing = degrees(bearing)
            bearing = (bearing + 360) % 360

            # make first span
            line = arcpy.Polyline(arcpy.Array([pnt_A, pnt_B]))
            if line.length < 8000:  # omits "false spans"
                icurs.insertRow((line, ID, 0.0, bearing, line.length))

            # sets next
            lat1 = lat2
            lon1 = lon2

        # all other towers
        else:
            # set 3rd coordinate variables
            ID += 1
            x3 = row[0][0]
            y3 = row[0][1]
            lat2 = radians(float(row[1]))  # Y
            lon2 = radians(float(row[2]))  # X
            pnt_C = arcpy.Point(x3, y3)

            # now that we have 2 spans/vectors we can
            # use dot product to find PLS angle
            # vectorA * vectorB / magnitudeA * magnitudeB
            #   vec[0]    vec[1]
            vecA = ((x2 - x1), (y2 - y1))
            vecB = ((x3 - x2), (y3 - y2))
            angle1 = atan(vecA[1] / vecA[0])
            angle2 = atan(vecB[1] / vecB[0])
            magA = sqrt((vecA[0] * vecA[0]) + (vecA[1] * vecA[1]))
            magB = sqrt((vecB[0] * vecB[0]) + (vecB[1] * vecB[1]))
            dot = ((vecA[0] * vecB[0]) + (vecA[1] * vecB[1])) / (magA * magB)

            # rare case for 0 angle
            dot = dot if dot < 1.0 else 0.9999

            # arccosine yields angle in radians
            arcCos = acos(dot)

            # convert radians to degrees
            degree = round(degrees(arcCos), 4)
            if flag == 1:
                degree = 0
                flag = 0

            # vecB bearings
            bearing = atan2(sin(lon2 - lon1) * cos(lat2),
                            cos(lat1) * sin(lat2) - sin(lat1) * cos(lat2) * cos(lon2 - lon1))
            bearing = degrees(bearing)
            bearing = (bearing + 360) % 360

            # insert data
            line = arcpy.Polyline(arcpy.Array([pnt_B, pnt_C]))
            if line.length < 8000:  # catches false spans
                icurs.insertRow((line, ID, degree, bearing, line.length))
            else:  # span is false
                arcpy.AddMessage("False span found at: " + str(ID) + "-" + str(ID + 1))
                branches.append((line, ID))  # keep record of false spans
                flag = 1

            # next
            x1 = x2
            y1 = y2
            x2 = x3
            y2 = y3
            pnt_A = pnt_B
            pnt_B = pnt_C
            lat1 = lat2
            lon1 = lon2

del icurs

# update pls angle
# if bearing turns left (-)
# if right (+)
with arcpy.da.UpdateCursor(spans, ["BEARING", "PLS_ANGLE"]) as cursor:
    for i, row in enumerate(cursor):
        if i == 0:
            angle1a = int(row[0])
            angle1b = ((angle1a + 180) + 360) % 360
        else:
            angle2 = int(row[0])
            if angle2 > angle1b:
                row[1] = row[1] * -1
                cursor.updateRow(row)
                if angle2 > angle1a and angle2 > angle1b:
                    if 180 <= angle1a <= 360:
                        row[1] = row[1] * -1
                        cursor.updateRow(row)
            if angle2 < angle1a and angle2 < angle1b:
                if 0 <= angle1a <= 180:
                    row[1] = row[1] * -1
                    cursor.updateRow(row)
            angle1a = angle2
            angle1b = ((angle1a + 180) + 360) % 360

# make bearing and distance table to create offset reference points
# a bearing table is used to make reference lines for attachments
# the bearing tool makes a polyline given a distance, bearing, and a start point
brngTbl = os.path.join("in_memory", "Bearing_Tbl")
arcpy.CreateTable_management("in_memory", "Bearing_Tbl")
arcpy.AddField_management(brngTbl, "ID", "DOUBLE")
arcpy.AddField_management(brngTbl, "X", "DOUBLE")
arcpy.AddField_management(brngTbl, "Y", "DOUBLE")
arcpy.AddField_management(brngTbl, "BEARING", "DOUBLE")
arcpy.AddField_management(brngTbl, "DISTANCE", "DOUBLE")

icurs = arcpy.da.InsertCursor(brngTbl, ["ID", "X", "Y", "BEARING", "DISTANCE"])

# get data from spans
spanList = [row[0] for row in arcpy.da.SearchCursor(spans, ["ID"])]

with arcpy.da.SearchCursor(spans, ["Shape@", "Id", "PLS_ANGLE", "BEARING"]) as cursor:
    for row in cursor:
        line = row[0]
        # get line points
        x1 = line.firstPoint.X
        y1 = line.firstPoint.Y
        x2 = line.lastPoint.X
        y2 = line.lastPoint.Y
        ID1 = row[1] + .1  # long
        ID2 = row[1] + .2  # trans

        # set bearings for both arms
        bearing1 = row[3]
        angle = row[2] / 2
        # change to positive if negative
        if angle < 0:
            angle = angle * -1
        # check if angle should be added to or subtracted from 
        if row[2] > 0:
            bearing2 = (bearing1 + 90) - angle  # long off1 ID1
        else:
            bearing2 = (bearing1 + 90) + angle  # long off1 ID1
        bearing3 = bearing2 + 180  # long off2 ID1
        bearing4 = bearing3 + 90  # trans off1 ID2
        bearing5 = bearing4 + 180  # trans off2 ID2

        # normalize possible over bearing
        bearing2 = round((bearing2 + 360) % 360, 2)
        bearing3 = round((bearing3 + 360) % 360, 2)
        bearing4 = round((bearing4 + 360) % 360, 2)
        bearing5 = round((bearing5 + 360) % 360, 2)

        # insert arm data into table
        icurs.insertRow((ID1, x1, y1, bearing2, 50))
        icurs.insertRow((ID1, x1, y1, bearing3, 50))
        icurs.insertRow((ID2, x1, y1, bearing4, 50))
        icurs.insertRow((ID2, x1, y1, bearing5, 50))

        # check if last tower
        if row[1] == max(spanList):
            bearing2 = bearing1
            bearing3 = bearing2 + 180
            bearing4 = bearing3 + 90
            bearing5 = bearing4 + 180
            bearing2 = round((bearing2 + 360) % 360, 2)
            bearing3 = round((bearing3 + 360) % 360, 2)
            bearing4 = round((bearing4 + 360) % 360, 2)
            bearing5 = round((bearing5 + 360) % 360, 2)

            icurs.insertRow((ID1 + 1, x2, y2, bearing2, 50))
            icurs.insertRow((ID1 + 1, x2, y2, bearing3, 50))
            icurs.insertRow((ID2 + 1, x2, y2, bearing4, 50))
            icurs.insertRow((ID2 + 1, x2, y2, bearing5, 50))

        # check if end of branch
        # since previous data excludes false span lines
        # we need to access the list of false span lines
        elif row[1] + 1 in [y[1] for y in branches]:  # if next span is in false span list
            i = [y[1] for y in branches].index(row[1] + 1)  # get index
            item = branches[i]  # get data at index
            line = item[0]  # get line geometry
            x3 = line.firstPoint.X  # get x
            y3 = line.firstPoint.Y  # get y
            icurs.insertRow((ID1 + 1, x3, y3, bearing2, 50))  # use current bearings
            icurs.insertRow((ID1 + 1, x3, y3, bearing3, 50))
            icurs.insertRow((ID2 + 1, x3, y3, bearing4, 50))
            icurs.insertRow((ID2 + 1, x3, y3, bearing5, 50))
del icurs

# make shapes from bearing table
crossArms = os.path.join("in_memory", "Axis_Lines")
arcpy.BearingDistanceToLine_management(brngTbl, crossArms, "X", "Y", "DISTANCE", "FEET", "BEARING", "DEGREES",
                                       "GEODESIC", "ID", CordSys)
crossArms_diss = os.path.join(OutFldr, "Tower_Axes.shp")
arcpy.Dissolve_management(crossArms, crossArms_diss, "ID")

# need to correct start and end points of reference lines 
# so offsets will be accurate
ucurs = arcpy.da.UpdateCursor(crossArms_diss, ["Shape@", "ID"])
with arcpy.da.SearchCursor(spans, ["Shape@", "ID", "BEARING"]) as cursor:
    for row in cursor:
        span = row[0]
        for item in ucurs:
            if item[1] == row[1] + .1:  # correct longit off lines
                longitLine = item[0]
                startPnt = longitLine.firstPoint
                endPnt = longitLine.lastPoint
                query = span.queryPointAndDistance(startPnt)  # query span line with start point of longit line
                lOrR = query[3]  # true if on right side of span
                if lOrR == False:  # if start point is on left side correct it
                    newLine = arcpy.Polyline(arcpy.Array([endPnt, startPnt]))
                    item[0] = newLine
                    ucurs.updateRow(item)
                    ucurs.reset()
                    break
                else:
                    ucurs.reset()
                    break
del ucurs

transLines = [row for row in arcpy.da.SearchCursor(crossArms_diss, ["Shape@", "ID"]) if str(row[1]).endswith(".1")]

with arcpy.da.UpdateCursor(crossArms_diss, ["Shape@", "ID"]) as cursor:
    for row in cursor:
        if str(row[1]).endswith(".2"):
            ID = round(row[1] - .1, 1)
            i = [y[1] for y in transLines].index(ID)
            longitLine = transLines[i][0]
            transLine = row[0]
            startPnt = transLine.firstPoint
            endPnt = transLine.lastPoint
            query = longitLine.queryPointAndDistance(startPnt)
            lOrR = query[3]
            if lOrR:  # if start point is on right side correct
                newLine = arcpy.Polyline(arcpy.Array([endPnt, startPnt]))
                row[0] = newLine
                cursor.updateRow(row)

# debugging: this visualizes the start and end points of a line
axisPnts = os.path.join(OutFldr, "Axis_pnts.shp")
arcpy.CreateFeatureclass_management(OutFldr, "Axis_pnts.shp", "POINT", "", "", "", CordSys)
arcpy.AddField_management(axisPnts, "TYPE", "TEXT")
icurs = arcpy.da.InsertCursor(axisPnts, ["Shape@XY", "TYPE"])
with arcpy.da.SearchCursor(crossArms_diss, "Shape@") as cursor:
    for row in cursor:
        startPntX = row[0].firstPoint.X
        startPntY = row[0].firstPoint.Y
        endPntX = row[0].lastPoint.X
        endPntY = row[0].lastPoint.Y
        icurs.insertRow(((startPntX, startPntY), "START"))
        icurs.insertRow(((endPntX, endPntY), "END"))
del icurs

#### formula for calculating destination point given bearing and distance
###lat2: =ASIN(SIN(lat1)*COS(d/R) + COS(lat1)*SIN(d/R)*COS(brng))
###lon2: =lon1 + ATAN2(COS(d/R)-SIN(lat1)*SIN(lat2), SIN(brng)*SIN(d/R)*COS(lat1))

''' Calculate attachment offsets '''

# add fields for attachment tower positions
arcpy.AddField_management(atchmts_twrs, "TRANS_OFF", "DOUBLE")
arcpy.AddField_management(atchmts_twrs, "LONGIT_OFF", "DOUBLE")
arcpy.AddField_management(atchmts_twrs, "DIST_BELOW", "DOUBLE")

# calculate trans offset
scurs = arcpy.da.SearchCursor(crossArms_diss, ["Shape@", "ID"])
#        0          1           2
with arcpy.da.UpdateCursor(atchmts_twrs, ["Shape@XY", "QSI_Tower", "TRANS_OFF"]) as cursor:
    for row in cursor:
        ins_X = row[0][0]
        ins_Y = row[0][1]
        ins_Pnt = arcpy.Point(ins_X, ins_Y)
        for item in scurs:
            # if attachment id = trans off reference line id
            if item[1] == row[1] + .2:
                query = item[0].queryPointAndDistance(ins_Pnt)
                pntB = query[0].centroid
                pntB_x = pntB.X
                pntB_y = pntB.Y
                dist = query[1]
                minD = query[2]
                lOrR = query[3]  # true if on right side
                # determine left or right side
                if lOrR == False:
                    minD = minD * -1
                row[2] = minD
                cursor.updateRow(row)
                break
        scurs.reset()
del scurs

# calculate dist below
with arcpy.da.UpdateCursor(atchmts_twrs, ["TWR_Z2", "INS_Z", "DIST_BELOW"]) as cursor:
    for row in cursor:
        z = row[0] - row[1]
        row[2] = z
        cursor.updateRow(row)

# calculate longit offsets
scurs = arcpy.da.SearchCursor(crossArms_diss, ["Shape@", "ID"])
#        0          1           2
with arcpy.da.UpdateCursor(atchmts_twrs, ["Shape@XY", "QSI_Tower", "LONGIT_OFF"]) as cursor:
    for row in cursor:
        ins_X = row[0][0]
        ins_Y = row[0][1]
        ins_Pnt = arcpy.Point(ins_X, ins_Y)
        for item in scurs:
            # if attachment id = long off reference line id
            if item[1] == row[1] + .1:
                query = item[0].queryPointAndDistance(ins_Pnt)
                pntB = query[0].centroid
                pntB_x = pntB.X
                pntB_y = pntB.Y
                dist = query[1]
                minD = query[2]
                lOrR = query[3]  # true if on right side
                if lOrR:  # == False:
                    minD = minD * -1
                row[2] = minD
                cursor.updateRow(row)
                break
        scurs.reset()
del scurs
