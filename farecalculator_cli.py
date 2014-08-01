import base64
from farecalculator import calculate_fare
import sys
import urllib2
import xml.etree.cElementTree as ET
from lxml import etree
try:
   from conf import NS_API_USERNAME,NS_API_PASSWORD
except:
   NS_API_USERNAME,NS_API_PASSWORD = ("No Config file supplied",)*2

authorization = base64.b64encode(NS_API_USERNAME+':'+NS_API_PASSWORD)

station_abbrv = {}

def load_stations():

    url = 'http://webservices.ns.nl/ns-api-stations'
    req = urllib2.Request(url)
    req.add_header("Authorization", "Basic %s" % authorization)
    response = urllib2.urlopen(req)
    root = etree.parse(response)
    for station in root.findall(".//station"):
        code = station.find('code').text.lower()
        name = station.find('name').text
        station_abbrv[name] = code

def calculate_journey(from_station,to_station):
    load_stations()
    url = 'http://webservices.ns.nl/ns-api-treinplanner?fromStation=%s&toStation=%s&previousAdvices=5&nextAdvices=5' % (from_station,to_station)
    req = urllib2.Request(url)
    req.add_header("Authorization", "Basic %s" % authorization)
    response = urllib2.urlopen(req)
    root = etree.parse(response)
    fare_sections_printed = set([])
    for reismogelijkheid in root.findall(".//ReisMogelijkheid"):
        journey = {'sections' : []}
        for reisdeel in reismogelijkheid.findall(".//ReisDeel"):
           reisstops = reisdeel.findall(".//ReisStop")
           section = {'fromStation' : station_abbrv[reisstops[0].find('Naam').text].lower(),
                      'toStation'   : station_abbrv[reisstops[-1].find('Naam').text].lower(),
                      'operator'    : reisdeel.find('Vervoerder').text.replace('Arriva','ARR').replace('Syntus','SYNTUS').replace('Valleilijn','CXX').replace('NS International','NS').replace('GVB','NS').replace('R-net','NS').replace('Breng','BRENG').replace('Veolia','VTN')}
           journey['sections'].append(section)
        fare = calculate_fare(journey)
        if str(fare['faresections']) in fare_sections_printed:
            continue
        fare_sections_printed.add(str(fare['faresections']))
        print '------------------'
        for fare_section in journey['faresections']:
            print '% 10s % 10s % 5s 1eklas %5.2f    2eklas %5.2f' % (fare_section['fromStation'],
                                                            fare_section['toStation'],
                                                            fare_section['operator'],
                                                            float(fare_section['price_first'])/100,
                                                            float(fare_section['price_second'])/100)
        print '1eklas %5.2f    2eklas %5.2f' % (float(journey['price_first'])/100,float(journey['price_second'])/100)
            
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print 'Usage python farecalculator.py fromStation toStation'
    else:
        calculate_journey(sys.argv[1],sys.argv[2])
