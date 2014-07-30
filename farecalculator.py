import sqlite3
import urllib2
import lxml
import xml.etree.cElementTree as ET
from lxml import etree
import sys

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

def calculate_transferless_fare(fare_sections):
    faresection = fare_sections[0]
    c = db.cursor()
    c.execute("""
SELECT d.distance,fareunits,price_2ndfull,price_1stfull,
       (( max(d.distance,d.min_distance) * c.price_first)+entrance_fee)  as totalkmprice_1,
       (( max(d.distance,d.min_distance) * c.price_second)+entrance_fee) as totalkmprice_2,
       c.price_first,
       c.price_second,
       min_fare
FROM distance d JOIN fareunit_price fp ON (fp.distance = d.distance OR (fp.distance = 250 AND d.distance > 250))
                JOIN concession c USING (concession)
WHERE from_station = ? AND to_station = ? AND operator = ?; """,(faresection['fromStation'],
                                                                 faresection['toStation'],
                                                                 faresection['operator'])   )
    res = c.fetchall()
    if len(res) == 0:
        return None #No fare found
    if len(res) > 1:
        raise Exception('NS Multiple fares found')
    distance,fareunits,price_2ndfull,price_1stfull,totalkmprice_1,totalkmprice_2,price_first,price_second,min_fare = res[0]
    c.close()
    print res[0]
    if fareunits:
        return (distance,price_1stfull,price_2ndfull)
    else:
        if min_fare != 'NULL' and min_fare > totalkmprice_1:
            totalkmprice_1 = min_fare
        if min_fare != 'NULL' and min_fare > totalkmprice_2:
            totalkmprice_2 = min_fare
        if price_first == 'NULL':
            totalkmprice_1 = None
        else:
            totalkmprice_1 = int(round(totalkmprice_1,0))
        totalkmprice_2 = int(round(totalkmprice_2,0))
        return (distance,totalkmprice_1,totalkmprice_2)


"""
Input a journey, a list of sections. A section is a dict, containing fromStation, toStation, operator.
Stationcodes have to be lowercase
"""
def calculate_fare(journey):
    faresections = sections_to_faresections(journey)
    if len(faresections) == 1:
        return calculate_transferless_fare(faresections)
    else:
        raise Exception('Only NS supported')

def calculate_journey(from_station,to_station):
    url = 'http://ews-rpx.ns.nl/mobile-api-planner?fromStation=%s&toStation=%s&departure=true&dateTime=2014-09-11T18:23&previousAdvices=6&nextAdvices=6&passing=true' % (from_station,to_station)
    req = urllib2.Request(url)
    req.add_header("Authorization", "Basic %s" % 'YW5kcm9pZDptdmR6aWc=')
    response = urllib2.urlopen(req)
    root = etree.parse(response)
    for reismogelijkheid in root.findall(".//ReisMogelijkheid"):
        journey = []
        for reisdeel in reismogelijkheid.findall(".//ReisDeel"):
           reisstops = reisdeel.findall(".//ReisStop")
           section = {'fromStation' : reisstops[0].find('Code').text.lower(),
                      'toStation'   : reisstops[-1].find('Code').text.lower(),
                      'operator'    : reisdeel.find('Vervoerder').text.replace('Arriva','ARR').replace('Syntus','SYNTUS').replace('Valleilijn','CXX').replace('NS International','NS').replace('GVB','NS').replace('R-net','NS').replace('Veolia','VTN')}
           journey.append(section)
        fare = calculate_fare(journey)
        print '------------------'
        print fare
        for prijs in reismogelijkheid.findall(".//Prijs"):
            if prijs.get('korting') != '0':
                continue
            print 'Klasse '+ prijs.get('klasse') + ' Korting '+prijs.get('korting') + ' prijs '+prijs.text
        print '------------------'
            

calculate_journey(sys.argv[1],sys.argv[2])
