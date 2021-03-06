from pubg_python import PUBG, Shard
from heatmappy import Heatmapper
from PIL import Image, ImageDraw
import sys, getopt
import math

API_KEY = ''

ERANGEL_MAP_IMG_PATH = 'data/img/erangel_map.jpg'
MIRAMAR_MAP_IMG_PATH = 'data/img/miramar_map.jpg'

MAPS_IMGS_PATHS = {'Desert_Main' : MIRAMAR_MAP_IMG_PATH, 'Erangel_Main' : ERANGEL_MAP_IMG_PATH}

def buildHeatMap(pointsList, circlesCoordsList, planePath, imgFile_path):
    mapimg = Image.open(imgFile_path)

    draw = ImageDraw.Draw(mapimg)

    # draw line of plane moving
    if len(planePath) == 2 and planePath[0] is not None and planePath[1] is not None:
        length = 2000
        starty = planePath[0][1] - length * math.sin(planePath[1])
        startx = planePath[0][0] - length * math.cos(planePath[1])
        endy = planePath[0][1] + length * math.sin(planePath[1])
        endx = planePath[0][0] + length * math.cos(planePath[1])
        draw.line(xy=[(startx, starty), (endx, endy)], width=3, fill=(0, 255, 255))

    for coordsAndRadius in circlesCoordsList:
        draw.ellipse([coordsAndRadius[0][0] - coordsAndRadius[1], coordsAndRadius[0][1] - coordsAndRadius[1],
                      coordsAndRadius[0][0] + coordsAndRadius[1], coordsAndRadius[0][1] + coordsAndRadius[1]],
                     outline='white')

    heatmapper = Heatmapper(point_diameter=25, point_strength=0.2, opacity=0.7)
    heatmapImg = heatmapper.heatmap_on_img(pointsList, mapimg)
    return heatmapImg

def getTelemetryPlayersCoords(telemetry):
    player_positions_events = telemetry.events_from_type('LogPlayerPosition')
    coordinatesList = []

    for pke in player_positions_events:
        if pke.elapsed_time > 0:
            x = round(pke.character.location.x / 600)
            y = round(pke.character.location.y / 600)
            coordinatesList.append((x, y))

    return coordinatesList

def getTelemetryMapName(telemetry):
    events = telemetry.events_from_type('LogPlayerPosition')
    return events[0].common.map_name

def getTelemetrySafeZonesLocations(telemetry):
    gameStatesEvents = telemetry.events_from_type('LogGameStatePeriodic')

    # need to select circles because api sends a lot of trash (intermediate circles)
    coordsDict = dict()
    for gs in gameStatesEvents:
        zoneCoords = [round(gs.game_state.safety_zone_position['x']/600), round(gs.game_state.safety_zone_position['y']/600),
                      round(gs.game_state.safety_zone_position['z'])]

        if zoneCoords[0] in coordsDict:
            coordsDict[zoneCoords[0]][0] += 1
        else:
            coordsDict[zoneCoords[0]] = [1, zoneCoords, round(gs.game_state.safety_zone_radius/600)]

    locationsAndRadii = []
    for key in coordsDict.keys():
        value = coordsDict[key]
        if value[0] > 3:
            locationsAndRadii.append((value[1], value[2]))

    return locationsAndRadii

def getTelemetryPlanePath(telemetry):
    player_positions_events = telemetry.events_from_type('LogPlayerPosition')

    planeZ = max(pke.character.location.z for pke in player_positions_events)
    positions_on_plane = [pos for pos in player_positions_events if pos.character.location.z == planeZ]

    x0 = positions_on_plane[0].character.location.x
    y0 = positions_on_plane[0].character.location.y
    x1 = positions_on_plane[-1].character.location.x
    y1 = positions_on_plane[-1].character.location.y

    angle = math.atan2(y1 - y0, x1 - x0)

    return [(round(x0 / 600), round(y0 / 600)), angle]

def getMatchHeatmap(api, match):
    """
    Make a heatmap of players activity of the match.

    :param match: pubg_python.match object
    :return: PIL Image
    """
    asset = match.assets[0]
    telemetry = api.telemetry(asset.url)

    mapName = getTelemetryMapName(telemetry)
    mapImgPath = MAPS_IMGS_PATHS[mapName]

    playersCoords = getTelemetryPlayersCoords(telemetry)
    circlesCoordsAndRadii = getTelemetrySafeZonesLocations(telemetry)
    planePath = getTelemetryPlanePath(telemetry)

    heatmapImg = buildHeatMap(playersCoords, circlesCoordsAndRadii, planePath, mapImgPath)

    return heatmapImg

def main(argv):
    player_name = ''
    server = None
    out_heatmap_file_name = ''

    match_number = 0

    try:
        opts, args = getopt.getopt(argv,"hp:s:o:m:",["playername=","server=","outputfile=","match"])
    except getopt.GetoptError:
        print('pubgheatmap.py -p <playername> -s <server> -o <outputfile>')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print('pubgheatmap.py -p <playername> -s <server> -o <outputfile>')
            print('Allowed servers: pc-as, pc-eu, pc-krjp, pc-na, pc-oc, pc-sa, pc-sea')
            print('Example: pubgheatmap.py -p tetraquark -s pc-eu -o heatmap.jpg')
            print('')
            sys.exit()
        elif opt in ("-p", "--playername"):
            player_name = arg
        elif opt in ("-s", "--server"):
            server = Shard(arg)
        elif opt in ("-o", "--outputfile"):
            out_heatmap_file_name = arg
        elif opt in ("-m", "--match"):
            match_number = int(arg)

    if not player_name or server is None:
        print('Forgot to enter the player name or server.')
        print('pubgheatmap.py -p <playername> -s <server> -o <outputfile>')
        sys.exit(2)

    print('Trying to get data from PUBG servers.')

    api = PUBG(API_KEY, server)

    # get required player
    players = api.players().filter(player_names=[player_name])
    myPlayer = players[0]

    # get the last player matches
    mathcesIdList = [match.id for match in myPlayer.matches]
    # get required match object
    match = api.matches().get(mathcesIdList[match_number])

    print('Done.')
    print('Trying to build the match heatmap.')

    # get match heatmap (PIL image file)
    heatmapImg = getMatchHeatmap(api=api, match=match)

    print('Done.')

    # save image to the file
    if not out_heatmap_file_name:
        out_heatmap_file_name = mathcesIdList[match_number] + '_heatmap.jpg'
    heatmapImg.save(out_heatmap_file_name)

if __name__ == "__main__":
    main(sys.argv[1:])
