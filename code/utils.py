import geopandas as gpd
import pandas as pd
import numpy as np
import movingpandas as mpd
import matplotlib
import matplotlib.pyplot as plt
import seaborn as sns
from tqdm import tqdm
import time
from osm2geojson.helpers import overpass_call
from osm2geojson.main import json2geojson
import warnings
warnings.filterwarnings('ignore')

# based on https://github.com/remisalmon/Strava-local-heatmap-browser
# dark (dark maps, e.g. CartoDB dark_matter), light (light maps, e.g. Stamen Terrain)
# original ("classic" heatmap)

HEATMAP_GRAD = {'dark':{0.0: '#000004',
                        0.1: '#160b39',
                        0.2: '#420a68',
                        0.3: '#6a176e',
                        0.4: '#932667',
                        0.5: '#bc3754',
                        0.6: '#dd513a',
                        0.7: '#f37819',
                        0.8: '#fca50a',
                        0.9: '#f6d746',
                        1.0: '#fcffa4'},
                 'light':{0.0: '#3b4cc0',
                          0.1: '#5977e3',
                          0.2: '#7b9ff9',
                          0.3: '#9ebeff',
                          0.4: '#c0d4f5',
                          0.5: '#dddcdc',
                          0.6: '#f2cbb7',
                          0.7: '#f7ac8e',
                          0.8: '#ee8468',
                          0.9: '#d65244',
                          1.0: '#b40426'},
                 'original':{0: 'black', 
                             0.6:'blue', 
                             0.7:'lime', 
                             0.8:'yellow', 
                             0.9:'orange', 
                             1:'red'}
                }


def ms_to_km(ms):

    v = (ms) * (60*60)/1000
    return v


def getTopLongestTravelTime(data, top):
    
    activities = dict()
    for i in range(len(data)):
        activities[i] = [data[i].get_duration(), data[i].tracks[0].type]

    v = sorted(activities.items(), key=lambda item: item[1][0], reverse=True)[:top]
    for j in range(top):
        print("{}° longest activity duration: {}, activity n° {}, type: {}".format(j+1, time.strftime('%H:%M:%S', time.gmtime(v[j][1][0])), v[j][0], v[j][1][1]))


def getTopLongestTravel(data, top):
    
    activities = dict()
    for i in range(len(data)):
        activities[i] = [data[i].length_3d(), data[i].tracks[0].type]

    v = sorted(activities.items(), key=lambda item: item[1][0], reverse=True)[:top]
    for j in range(top):
        print("{}° longest activity length: {}, activity n° {}, type: {}".format(j+1, round((v[j][1][0]), 2), v[j][0], v[j][1][1]))


def getTopElevationDifference(data, top):

    activities = dict()
    for i in range(len(data)):
        activities[i] = [data[i].get_elevation_extremes().maximum - data[i].get_elevation_extremes().minimum, data[i].tracks[0].type]

    v = sorted(activities.items(), key=lambda item: item[1][0], reverse=True)[:top]
    for j in range(top):
        print("{}° highest elevation difference: {}, activity n° {}, type: {}".format(j+1, round((v[j][1][0]), 2), v[j][0], v[j][1][1]))


def toList(activities) -> list:

    target = []
    for activity in tqdm(activities):
        #print(activity)
        data = []
        for point_idx, point in enumerate(activity.tracks[0].segments[0].points):
            data.append([point.longitude, point.latitude, point.elevation, point.time])

        cols = ['longitude', 'latitude', 'elevation', 'time']
        gpx_track = pd.DataFrame(data, columns=cols)
        gpx_track.time = gpx_track.time.apply(lambda x: x.replace(tzinfo=None))
        target.append(gpx_track)

    return target


def toGdfList(activities_dfList) -> list:

    target_gdfList = []
    for i in tqdm(range(len(activities_dfList))):
        geo_df = gpd.GeoDataFrame(activities_dfList[i], crs=4326, geometry=gpd.points_from_xy(activities_dfList[i].longitude, activities_dfList[i].latitude, activities_dfList[i].elevation))
        # geo_df.set_index('time', drop=True, inplace=True)
        target_gdfList.append(geo_df)

    return target_gdfList


def getTrajList(geo_dfList) -> list:

    trajectories = []
    for i in range(len(geo_dfList)):
        trajectory = mpd.Trajectory(geo_dfList[i], i)
        trajectories.append(trajectory)

    return trajectories


def get_boundary(city: str):

    boundary = gpd.GeoDataFrame()
    print("Getting boundaries for {}".format(city))

    query = '''
        [out:json];
        area[name="{}"][admin_level=8][boundary=administrative]->.target;
        area["name"="Italia"][boundary=administrative]->.wrap;
        rel(pivot.target)(area.wrap);

        out geom;
    '''.format(city)

    ti = time.time()
    result = overpass_call(query)
    res = json2geojson(result)
    boundary = boundary.append(gpd.GeoDataFrame.from_features(res), ignore_index=True)
    boundary.set_crs(epsg=4326, inplace=True)
    #coords = [i for i in boundary.to_crs(epsg=3587).geometry[0].envelope.exterior.coords]

    if len(boundary) <= 0:
        raise ConnectionError("No boundaries were found for {}. Try with another city or check your Overpass query limit.".format(city))
    else:
        print("Extracted boundaries for {}. Time elapsed: {} s".format(city, round(time.time()-ti, 2)))        

    #return min(coords[0][0], coords[2][0]), max(coords[0][0], coords[2][0]), min(coords[0][1], coords[2][1]), max(coords[0][1], coords[2][1])
    return boundary


def getStopElevationDiff(stop_points, start) -> gpd.GeoDataFrame:

    stop_points['elevation_diff'] = 0.0
    stop_points['time_diff'] = stop_points.end_time[0] - stop_points.start_time[0]
    
    for i in range(len(stop_points)):
        if i==0:
            stop_points.elevation_diff[i] = np.round(stop_points.geometry[i].z - start.df.elevation[0], 2)
            stop_points.time_diff[i] = stop_points.start_time[i] - start.df.index[0]
        else:
            stop_points.elevation_diff[i] = np.round(stop_points.geometry[i].z - stop_points.geometry[i-1].z, 2)
            stop_points.time_diff[i] = stop_points.start_time[i] - stop_points.end_time[i-1]
    
    return stop_points


def plotHex(data, data_extent, basemap, basemap_extent, hex):
    
    f, ax = plt.subplots(1, figsize=(12, 12))
    ax.imshow(basemap, extent=basemap_extent, interpolation='bilinear')
    # Generate and add hexbin with hex hexagons in each 
    # dimension, no borderlines, 60% transparency (alpha),
    # and the reverse Oranges colormap
    hb = ax.hexbin(x=data['x'], 
                y=data['y'],
                gridsize=hex, linewidths=0,
                alpha=0.6, cmap='Reds')
    ax.axis(data_extent)
    plt.colorbar(hb)
    ax.set_axis_off()
    plt.show()


def plotKDE(data, data_extent, basemap, basemap_extent, grad):

    f, ax = plt.subplots(1, figsize=(15, 15))
    ax.imshow(basemap, extent=basemap_extent, interpolation='bilinear')
    # Generate and add KDE with a shading of grad gradients 
    # coloured contours, 30% of transparency (alpha),
    # and the reverse Reds colormap
    sns.kdeplot(x=data['x'], y=data['y'],
                    n_levels=grad, shade=True,
                    alpha=0.3, cmap='Reds')
    ax.axis(data_extent)
    ax.set_axis_off()
    plt.show()


def plotClusters(data, labels, basemap, basemap_extent):

    colors = ['grey','yellow','blue','purple', 'red', 'orange', 'green']
    f, ax = plt.subplots(1, figsize=(12, 12))
    ax.imshow(basemap, extent=basemap_extent, interpolation='bilinear')
    ax.scatter(data['x'], data['y'], \
    c=labels, cmap=matplotlib.colors.ListedColormap(colors), linewidth=0)

    ax.set_axis_off()
    plt.show()


def plotRunComparison(data):

    fig, axs = plt.subplots(3, sharex=True, figsize=(15,10))
    fig.suptitle('Running performances comparison')
    x = data.date
    axs[0].plot(x, data.length, color='orange')
    axs[0].set_ylabel('km', color='black')  
    axs[0].grid(b=True, which='both', axis='both')
    axs[1].plot(x, data.avgPace, color='blue')
    axs[1].set_ylabel('km/h', color='black')
    axs[1].grid(b=True, which='both', axis='both')
    axs[2].plot(x, data.vo2MaxValue, color='red')
    axs[2].set_ylabel('ml/kg/min', color='black')
    axs[2].grid(b=True, which='both', axis='both')
    axs[2].set_xlabel('date')

    for ax in axs:
        ax.xaxis.set_major_locator(plt.MaxNLocator(25))
        ax.label_outer()

    plt.xticks(rotation='vertical')

    plt.show()