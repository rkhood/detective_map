import geopandas as gpd
import numpy as np
import pandas as pd

import folium
import json
import re
import requests
import spacy
import wikipedia

from bs4 import BeautifulSoup
from collections import defaultdict
from folium.plugins import MarkerCluster
from urllib.request import urlopen


def scrape_shows():
    w = ('https://en.wikipedia.org/wiki/'
         'Category:British_detective_television_series')

    r = requests.get(w)
    soup = BeautifulSoup(r.text, 'lxml')
    sub_soup = soup.select('.mw-category')
    links = [a.get('title') for a in sub_soup[0].find_all('a')
            if a.has_attr('href')]
    return links


def spacy_locs(shows):
    nlp = spacy.load('en_core_web_sm')

    for show in shows:
        print(show)
        doc = nlp(wikipedia.WikipediaPage(title=show).summary)
        for entity in doc.ents:
            if entity.label_ == 'LOC':
                print(entity.text)


def lookup_locs(shows):
    locations = {}
    possible_locs = pd.read_csv('data/Towns_List.csv')
    for show in shows:
        text = wikipedia.WikipediaPage(title=show).content
        text = re.sub(r'[^\w\s]', ' ', text)
        words = re.findall(r'(?:(?<=^)|(?<=[^.]))\s+([A-Z][a-z]+)', text)
        locs = list(set(
            possible_locs[possible_locs.isin(words).any(1)]['County']))
        if locs:
            locations[show] = locs
    return locations


def get_locs_from_nlp():
    return lookup_locs(scrape_shows())


def make_map():
    geojson = ('https://opendata.arcgis.com/datasets/'
               'f3c8abecb0144417856378122eb7025f_0.geojson')
    with urlopen(geojson) as response:
        county_info = json.load(response)

    gdf = gpd.GeoDataFrame.from_features(county_info)
    gdf['centroid_lon'] = gdf['geometry'].centroid.x
    gdf['centroid_lat'] = gdf['geometry'].centroid.y
    gdf.crs = {'init':'epsg:4326'}

    df = pd.read_csv('data/shows_and_locs.csv')
    def get_locs_from_csv(df, x):
        county_list = df['Title'][df['County'].str.contains(x)].tolist()
        return county_list, len(county_list)

    gdf['shows'], gdf['num_shows'] = zip(
            *gdf['ctyua19nm'].apply(lambda x: get_locs_from_csv(df, x)))

    m = folium.Map(location=[np.median(gdf['centroid_lat'].tolist()),
                            np.median(gdf['centroid_lon'].tolist())],
                tiles='Stamen Toner', zoom_start=8)

    m.choropleth(
        geo_data=county_info,
        name='UK Detective shows',
        data=gdf,
        columns=['ctyua19nm', 'num_shows'],
        fill_color='YlOrRd',
        key_on='feature.properties.ctyua19nm',
        legend_name='Number of shows',
        threshold_scale=[0, 1, 2, 3, 4, 5, 10, 30, 53],
    )

    marker_cluster = MarkerCluster().add_to(m)
    for lat, lon, val, name, shows in zip(gdf['centroid_lat'].tolist(),
                                    gdf['centroid_lon'].tolist(),
                                    gdf['num_shows'].tolist(),
                                    gdf['ctyua19nm'].tolist(),
                                    gdf['shows'].tolist()):
        if val > 0:
            string = '<ul>\n'
            string += '\n'.join(['<li>' + str(s) + '</li>' for s in shows])
            string += '\n</ul>'

            html = f'''
            <h2>{name}<\h2>
            <h4>Num shows: {val} <\h4>
            <h4>Shows: {string} <\h4>
            '''
            folium.Marker(
                    location=[lat, lon],
                    popup=html,
                    ).add_to(marker_cluster)
    folium.LayerControl().add_to(m)
    m.save('map.html')


if __name__ == '__main__':

    make_map()
