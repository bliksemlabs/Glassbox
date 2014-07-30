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
    if faresection['operator'] == 'NS':
        c = db.cursor()
        res = c.execute("""
SELECT distance,price_2ndfull,price_2nd20,price_2nd40,price_1stfull,price_1st20,price_1st40
FROM distance JOIN fareunit_price USING (distance)
WHERE from_station = ? AND to_station = ? AND operator = 'NS'""",(faresection['fromStation'],faresection['toStation'])).fetchall()
        if len(res) == 0:
            return None #No fare found
        if len(res) > 1:
            raise Exception('NS Multiple fares found')
        c.close()
        return res
    else:
        raise Exception('Only NS supported')

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
                      'operator'    : reisdeel.find('Vervoerder').text.replace('Arriva','ARR').replace('Syntus','SYNTUS').replace('Valleilijn','CXX').replace('NS International','NS').replace('GVB','NS').replace('R-net','NS')}
           journey.append(section)
        fare = calculate_fare(journey)
        print '------------------'
        print fare
        for prijs in reismogelijkheid.findall(".//Prijs"):
            print 'Klasse '+ prijs.get('klasse') + ' Korting '+prijs.get('korting') + ' prijs '+prijs.text
        print '------------------'
            

calculate_journey(sys.argv[1],sys.argv[2])
