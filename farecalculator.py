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

#Return distance,whether fare units used, 2nd class fareunits price, 1st class fareunits price, KM-price first, KM-price second,
# minimum fare in concession, entrance fee for concession, minimum distance and the name of the concession for the fare_section
def fare_for_section(fare_section,first_section=False):
    c = db.cursor()
    c.execute("""
SELECT d.distance,calc_method,
       c.price_first,
       c.price_second,
       min_fare,
       entrance_fee,
       coalesce(min_distance,0),concession
FROM distance d JOIN concession c USING (concession)
WHERE from_station = ? AND to_station = ? AND operator = ?; """,(fare_section['fromStation'],
                                                                 fare_section['toStation'],
                                                                 fare_section['operator'])   )
    res = c.fetchall()
    if len(res) == 0:
        return None #No fare found
    c.close()
    return res[0]

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
def compute_km_fare(km_price,distance,units_passed):
    fare = 0.0
    for stage_ceiling in [40,80,100,120,150,200,250]:
        if distance == 0:
            break
        capacity = stage_ceiling - units_passed
        if capacity < 0:
            continue
        fare += lak_factor(stage_ceiling)*km_price*min(capacity,distance)
        distance -= min(capacity,distance)
        units_passed += capacity
    #Above 250 free
    return fare

compute_km_fare(17.1,106,0)

def round_op(price,operator):
    if operator == 'ARR':
        return int(price)
    return int(round(price))

def fare_for_distance(distance,fareunits_passed,calc_method,km_price_first,km_price_second,min_distance,min_fare,entrance_rate):
    if calc_method == 'TE':
        c = db.cursor()
        c.execute("SELECT price_1stfull,price_2ndfull FROM fareunit_price WHERE distance = ? OR (? > 250 AND distance = 250)",(distance,)*2)
        return c.fetchone()
    elif calc_method == 'TE_ARR':
        c = db.cursor()
        c.execute("SELECT price_1stfull,price_2ndfull FROM arr_fareunit_price WHERE distance = ? OR (? > 250 AND distance = 250)",(distance,)*2)
        return c.fetchone()
    elif calc_method == 'EASY_TRIP':
        distance = max(min_distance,distance)

        if km_price_first is None:
            km_price_first = 1.7*km_price_second
        price_first = entrance_rate + compute_km_fare(km_price_first,distance,fareunits_passed)
        price_second = entrance_rate + compute_km_fare(km_price_second,distance,fareunits_passed)

        return (price_first,price_second)
    elif calc_method == 'MIN_FARE': #Used on Valleilijn First x kilometers account for price y, rest (distance-x)*km_price
        price_first,price_second = 0,0
        
        price_second += min_fare
        price_first  += int(min_fare*1.7)
        distance = max(0,distance-min_distance)
        
        price_second += compute_km_fare(km_price_second,distance,8)
        price_first += compute_km_fare(km_price_first,distance,8)
        return (price_first,price_second)
    else:
        raise Exception("Unknown calculation method %s" % (calc_method))

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
        distance,calc_method,kmprice_first,kmprice_second,min_fare,entrance_fee,min_distance,concession = fare
       
        full_fare = fare_for_distance(distance+fareunits_passed,0,calc_method,
                                      kmprice_first,kmprice_second,min_distance,
                                      min_fare,entrance_fee)
        if full_fare is None:
           raise Exception('FARE NOT FOUND')
        full_first,full_second = full_fare
        section_first,section_second = (round_op(price,fare_section['operator']) for price in (full_first,full_second))

        if i > 0:
            passed_fare = fare_for_distance(fareunits_passed,0,calc_method,
                                            kmprice_first,kmprice_second,min_distance,
                                            min_fare,entrance_fee)

            passed_first,passed_second = passed_fare
            section_first,section_second = (round_op(price,fare_section['operator']) for price in (full_first-passed_first,full_second-passed_second))

        fare_section['price_first'],fare_section['price_second'] = section_first,section_second
        fareunits_passed += distance
        price_first += fare_section['price_first']
        price_second += fare_section['price_second']
        fare_section['fare_distance'] = distance
    journey['fare_distance'] = fareunits_passed
    journey['price_second'] = price_second
    journey['price_first'] = price_first
    return journey
