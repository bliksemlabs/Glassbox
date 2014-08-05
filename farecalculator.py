"""
The MIT License (MIT)

Copyright (c) 2014 Thomas Koch

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import sqlite3
import sys
import math

db = sqlite3.connect('data.db')

#Transform a journey into faresections per operator.
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

#Return NS firstclass,secondclass unit price for distance given
def unitprice(distance):
    c = db.cursor()
    c.execute("""
SELECT price_1stfull,price_2ndfull FROM fareunit_price WHERE distance = ? or (? > 250 and distance = 250)""",(distance,)*2)
    return c.fetchone()

#Return distance,whether fare units used, 2nd class fareunits price, 1st class fareunits price, KM-price first, KM-price second,
# minimum fare in concession, entrance fee for concession, minimum distance and the name of the concession for the fare_section
def fare_for_section(fare_section,first_section=False):
    c = db.cursor()
    c.execute("""
SELECT d.distance,fareunits,price_2ndfull,price_1stfull,
       c.price_first,
       c.price_second,
       min_fare,
       entrance_fee,
       coalesce(min_distance,0),concession
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
    distance,fareunits,price_2ndfull,price_1stfull,price_first,price_second,min_fare,entrance_fee,min_distance,concession = res[0]
    if concession == 'NOORD':
        c.execute("SELECT price_2ndfull,price_1stfull FROM arr_fareunit_price WHERE distance = ?",[distance])
        price_2ndfull,price_1stfull = c.fetchone()
    c.close()
    if fareunits:
        return (True,distance,price_1stfull,price_2ndfull,None,None,None,None,None,concession)
    else:
        return (False,distance,None,None,price_first,price_second,int(entrance_fee),min_fare,min_distance,concession)

#Return the LAK discount factor for the distance given
def lak_factor(distance):
    if distance <= 40:
        return 1
    elif distance <= 80:
        return 0.9680
    elif distance <= 100:
        return 0.8470
    elif distance <= 120:
        return 0.7
    elif distance <= 150:
        return 0.48
    elif distance <= 200:
        return 0.4
    elif distance <= 250:
        return 0.15
    elif distance > 250:
        return 0

#Compute the total fare using KM price, using LAK distance stages
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
        fare = fare_for_section(fare_section)
        if fare is None:
            print fare_section #Debug print
        fare_unit,distance,price_1stfull,price_2ndfull,kmprice_first,kmprice_second,entrance_free,min_fare,min_distance,concession = fare
        fare_section['fare_distance'] = distance
        if fare_unit:
            if i != 0:
                complete_1stfull,complete_2ndfull = unitprice(distance+fareunits_passed)
                passed_1stfull,passed_2ndfull = unitprice(fareunits_passed)
                fare_section['price_first'] = complete_1stfull-passed_1stfull
                fare_section['price_second'] = complete_2ndfull-passed_2ndfull
            else:
                fare_section['price_first'] = price_1stfull
                fare_section['price_second'] = price_2ndfull
        else:
            section_distance = distance
            
            section_first = 0
            section_second = 0

            if i==0 and min_fare is None:
                section_first  += entrance_free
                section_second += entrance_free

            #Valleilijn fare calculation, x min_distance and then if (distance-min_distance) > 0 (distance-min_distance)*km_price
            if fareunits_passed == 0 and min_distance is not None and min_fare is not None: 
               section_distance = max(section_distance-min_distance+1,0)
               x,min_fare = unitprice(min_distance)
               section_second += min_fare
               section_first  += int(min_fare*1.7)
            #Set fare-distance to min_distance
            elif distance+fareunits_passed < min_distance:
                section_distance = min_distance

            if kmprice_first is None:
                kmprice_first = kmprice_second
            section_first  += magic_round(compute_total_km_fare(kmprice_first,section_distance,fareunits_passed),fare_section['operator'])
            section_second += magic_round(compute_total_km_fare(kmprice_second,section_distance,fareunits_passed),fare_section['operator'])

            if i == len(journey['faresections']) - 1:
                full_second = compute_total_km_fare(kmprice_second,section_distance+fareunits_passed,0)
                if full_second < section_second + price_second:
                    section_second = max(0,magic_round(full_second - price_second,fare_section['operator']))
                full_first = compute_total_km_fare(kmprice_first,section_distance+fareunits_passed,0)
                if full_first < section_first + price_first:
                    section_first = max(0,magic_round(full_first - price_first,fare_section['operator']))

            fare_section['price_first'] = section_first
            fare_section['price_second'] = section_second

        fareunits_passed += fare_section['fare_distance']
        price_first += fare_section['price_first']
        price_second += fare_section['price_second']
    journey['fare_distance'] = fareunits_passed
    journey['price_second'] = price_second
    journey['price_first'] = price_first
    return journey
