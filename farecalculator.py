import sqlite3
import urllib2
import lxml
import xml.etree.cElementTree as ET
from lxml import etree
import sys
import math

db = sqlite3.connect('data.db')

def sections_to_faresections(journey):
    fare_sections = []

    from_station = None
    to_station = None
    last_operator = None
    for section in journey:
        if from_station is None:
            from_station = section['fromStation']
            to_station = section['toStation']
            last_operator = section['operator']
        elif last_operator != section['operator']:
            fare_sections.append( {'fromStation' : from_station, 'toStation' : to_station, 'operator' : last_operator} )
            from_station = section['fromStation']
            to_station = section['toStation']
            last_operator = section['operator']
        else:
            to_station = section['toStation']
    fare_sections.append( {'fromStation' : from_station, 'toStation' : to_station, 'operator' : last_operator} )
    return fare_sections

def fare_for_section(fare_section,first_section=False):
    c = db.cursor()
    c.execute("""
SELECT d.distance,fareunits,price_2ndfull,price_1stfull,
       max(d.distance,coalesce(d.min_distance,0)) * c.price_first  as totalkmprice_1,
       max(d.distance,coalesce(d.min_distance,0)) * c.price_second as totalkmprice_2,
       c.price_first,
       c.price_second,
       min_fare,
       entrance_fee
FROM distance d JOIN fareunit_price fp ON (fp.distance = d.distance OR (fp.distance = 250 AND d.distance > 250))
                JOIN concession c USING (concession)
WHERE from_station = ? AND to_station = ? AND operator = ?; """,(fare_section['fromStation'],
                                                                 fare_section['toStation'],
                                                                 fare_section['operator'])   )
    res = c.fetchall()
    if len(res) == 0:
        return None #No fare found
    if len(res) > 1:
        raise Exception('NS Multiple fares found')
    distance,fareunits,price_2ndfull,price_1stfull,totalkmprice_1,totalkmprice_2,price_first,price_second,min_fare,entrance_fee = res[0]
    c.close()
    if fareunits:
        fare_section['price_first'] = price_1stfull
        fare_section['price_second'] = price_2ndfull
        fare_section['fare_distance'] = distance
        fare_section['_fare_units'] = True
        fare_section['_km-price_first'] = None
        fare_section['_km-price_second'] = None
        return fare_section
    else:
        print fare_section
        print res[0]
        if first_section:
           totalkmprice_2 += entrance_fee
        if first_section and price_first != 'NULL':
           totalkmprice_1 += entrance_fee
        if min_fare != 'NULL' and min_fare > totalkmprice_1:
            totalkmprice_1 = min_fare
        if min_fare != 'NULL' and min_fare > totalkmprice_2:
            totalkmprice_2 = min_fare
        if price_first == 'NULL' or totalkmprice_1 is None:
            totalkmprice_1 = None
        else:
            fare_section['price_first'] = int(round(totalkmprice_1,0))
        fare_section['price_second'] = int(round(totalkmprice_2,0))
        fare_section['fare_distance'] = distance
        fare_section['_fare_units'] = False
        fare_section['_km-price_first'] = price_first
        fare_section['_km-price_second'] = price_second
        return fare_section

def calculate_fare_of_sections(journey):
    journey['fare_distance'] = 0
    journey['price_second'] = 0
    journey['price_first'] = 0
    
    for i,section in enumerate(journey['faresections']):
        fare_section = fare_for_section(section,first_section=(i==0))
        if fare_section is None:
            print section
            raise Exception('fare not found')
        journey['fare_distance'] += section['fare_distance']
        journey['price_second'] += section['price_second']
        if 'price_first' in section:
            journey['price_first'] += section['price_first']
        else:
            journey['price_first'] += section['price_second']

def lak(after_fareunits):
    if after_fareunits <= 40:
        return 1
    elif after_fareunits <= 80:
        return 0.9680
    elif after_fareunits <= 100:
        return 0.8470
    elif after_fareunits <= 120:
        return 0.7
    elif after_fareunits <= 150:
        return 0.48
    elif after_fareunits <= 200:
        return 0.4
    elif after_fareunits <= 250:
        return 0.15
    elif after_fareunits > 250:
        return 0

def apply_discount(journey):
    fareunits_passed = 0
    journey['price_second'] = 0
    journey['price_first'] = 0

    for i,fare_section in enumerate(journey['faresections']):
        if i != 0:
            if fare_section['_fare_units']:
                fare_section['price_second'] *= lak(fareunits_passed)
                fare_section['price_first'] *= lak(fareunits_passed)
            else:
                km_price_second = fare_section['_km-price_second'] * lak(fareunits_passed)
                fare_section['price_second'] = int(km_price_second * fare_section['fare_distance'])

                km_price_first = fare_section['_km-price_first'] * lak(fareunits_passed)
                fare_section['price_first'] = int(km_price_first * fare_section['fare_distance'])

        fareunits_passed += fare_section['fare_distance']
        journey['price_second'] += fare_section['price_second']
        journey['price_first'] += fare_section['price_first']
        #for key,value in fare_section.items() : 
            #if key.startswith('_') : del fare_section[key] #Remove hidden values
    return journey

"""
Input a journey, a list of sections. A section is a dict, containing fromStation, toStation, operator.
Stationcodes have to be lowercase
"""
def calculate_fare(journey):
    journey['faresections'] = sections_to_faresections(journey['sections'])
    calculate_fare_of_sections(journey)
    if len(journey['faresections']) == 1:
        for key,value in journey['faresections'][0].items() : 
            if key.startswith('_') : del journey['faresections'][0][key] #Remove hidden values
        return journey
    return apply_discount(journey)

def calculate_journey(from_station,to_station):
    url = 'http://ews-rpx.ns.nl/mobile-api-planner?fromStation=%s&toStation=%s&departure=true&dateTime=2014-09-11T18:23&previousAdvices=6&nextAdvices=6&passing=true' % (from_station,to_station)
    req = urllib2.Request(url)
    req.add_header("Authorization", "Basic %s" % 'YW5kcm9pZDptdmR6aWc=')
    response = urllib2.urlopen(req)
    root = etree.parse(response)
    for reismogelijkheid in root.findall(".//ReisMogelijkheid"):
        journey = {'sections' : []}
        for reisdeel in reismogelijkheid.findall(".//ReisDeel"):
           reisstops = reisdeel.findall(".//ReisStop")
           section = {'fromStation' : reisstops[0].find('Code').text.lower(),
                      'toStation'   : reisstops[-1].find('Code').text.lower(),
                      'operator'    : reisdeel.find('Vervoerder').text.replace('Arriva','ARR').replace('Syntus','SYNTUS').replace('Valleilijn','CXX').replace('NS International','NS').replace('GVB','NS').replace('R-net','NS').replace('Breng','BRENG').replace('Veolia','VTN')}
           journey['sections'].append(section)
        fare = calculate_fare(journey)
        print '------------------'
        print fare
        for prijs in reismogelijkheid.findall(".//Prijs"):
            if prijs.get('korting') != '0':
                continue
            print 'Klasse '+ prijs.get('klasse') + ' Korting '+prijs.get('korting') + ' prijs '+prijs.text
        print '------------------'
            

calculate_journey(sys.argv[1],sys.argv[2])
