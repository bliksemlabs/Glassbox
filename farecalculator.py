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

def unitprice(distance):
    c = db.cursor()
    c.execute("""
SELECT price_1stfull,price_2ndfull FROM fareunit_price WHERE distance = ? or (? > 250 and distance = 250)""",(distance,)*2)
    return c.fetchone()

def fare_for_section(fare_section,first_section=False):
    c = db.cursor()
    c.execute("""
SELECT d.distance,fareunits,price_2ndfull,price_1stfull,
       c.price_first,
       c.price_second,
       min_fare,
       entrance_fee,
       coalesce(min_distance,0)
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
    distance,fareunits,price_2ndfull,price_1stfull,price_first,price_second,min_fare,entrance_fee,min_distance = res[0]
    c.close()
    if fareunits:
        return (True,distance,price_1stfull,price_2ndfull,None,None,None,None,None)
    else:
        if price_first is None or price_first == 'NULL':
            price_first = None
        return (False,distance,None,None,price_first,price_second,int(entrance_fee),min_fare,min_distance)

def lak_factor(ceiling):
    if ceiling <= 40:
        return 1
    elif ceiling <= 80:
        return 0.9680
    elif ceiling <= 100:
        return 0.8470
    elif ceiling <= 120:
        return 0.7
    elif ceiling <= 150:
        return 0.48
    elif ceiling <= 200:
        return 0.4
    elif ceiling <= 250:
        return 0.15
    elif ceiling > 250:
        return 0

def compute_total_km_fare(km_price,distance,units_passed):
    fare = 0.0
    for stage_ceiling in [40,80,100,120,150,200,250]:
        if distance == 0:
            break
        capacity = stage_ceiling - units_passed
        if capacity < 0:
            continue
        fare += lak_factor(stage_ceiling)*km_price*min(capacity,distance)
        distance -= min(capacity,distance)
        units_passed += min(capacity,distance)
    #Above 250 free
    return fare

def magic_round(price,operator):
    if operator == 'VTN':
        return int(price)
    return int(round(price))    

"""
Input a journey, a list of sections. A section is a dict, containing fromStation, toStation, operator.
Stationcodes have to be lowercase
"""
def calculate_fare(journey):
    journey['faresections'] = sections_to_faresections(journey['sections'])
    fareunits_passed = 0
    price_second = 0
    price_first = 0
    for i,fare_section in enumerate(journey['faresections']):
        fare_unit,distance,price_1stfull,price_2ndfull,kmprice_first,kmprice_second,entrance_free,min_fare,min_distance = fare_for_section(fare_section)
        fare_section['fare_distance'] = distance
        if fare_unit:
            if fareunits_passed > 0:
                complete_1stfull,complete_2ndfull = unitprice(distance+fareunits_passed)
                passed_1stfull,passed_2ndfull = unitprice(fareunits_passed)
                fare_section['price_first'] = complete_1stfull-passed_1stfull
                fare_section['price_second'] = complete_2ndfull-passed_2ndfull
            else:
                fare_section['price_first'] = price_1stfull
                fare_section['price_second'] = price_2ndfull
        else:
            section_distance = distance
            if distance+fareunits_passed < min_distance:
                section_distance = min_distance
            if kmprice_first is None: #No known KM price for 1st class, fallback to 2nd
                fare_section['price_first']  = magic_round(compute_total_km_fare(kmprice_second,section_distance,fareunits_passed),fare_section['operator'])
            else:
                fare_section['price_first']  = magic_round(compute_total_km_fare(kmprice_first,section_distance,fareunits_passed),fare_section['operator'])
            fare_section['price_second'] = magic_round(compute_total_km_fare(kmprice_second,section_distance,fareunits_passed),fare_section['operator'])
            if i==0:
                fare_section['price_first'] += entrance_free
                fare_section['price_second'] += entrance_free

        fareunits_passed += fare_section['fare_distance']
        price_first += fare_section['price_first']
        price_second += fare_section['price_second']

    journey['fare_distance'] = fareunits_passed
    journey['price_second'] = price_second
    journey['price_first'] = price_first
    return journey

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
            second_matches=False
            first_matches=False
            if prijs.get('klasse') == '1':
                ns_prijs = int(round(float(prijs.text)*100))
                print '1: NS-prijs %s Eigenprijs %s Match = %s, diff %s' % (ns_prijs,fare['price_first'],ns_prijs==fare['price_first'],ns_prijs-fare['price_first'])
            if prijs.get('klasse') == '2':
                ns_prijs = int(round(float(prijs.text)*100))
                print '2: NS-prijs %s Eigenprijs %s Match = %s, diff %s' % (ns_prijs,fare['price_second'],ns_prijs==fare['price_second'],ns_prijs-fare['price_second'])
            

calculate_journey(sys.argv[1],sys.argv[2])
