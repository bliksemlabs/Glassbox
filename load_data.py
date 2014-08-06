import sqlite3
import os

try:
    os.remove('data.db')
except:
    pass

db = sqlite3.connect('data.db')

c = db.cursor()

c.execute("CREATE TABLE distance ( from_station TEXT, to_station TEXT, distance integer, operator TEXT, min_distance integer);")
c.execute("CREATE index distance_idx ON DISTANCE (from_station,to_station);")
for line in open('data/distance.csv'):
    values = line[:-1].split(',')
    c.execute("INSERT INTO distance (from_station,to_station, distance, operator) VALUES (?,?,?,?)",values)

c.execute(
"""
CREATE TABLE fareunit_price (
key TEXT,
distance integer,
price_2ndfull integer,
price_2nd20 integer,
price_2nd40 integer,
price_1stfull integer,
price_1st20 integer,
price_1st40 integer
);""")
c.execute("CREATE INDEX fareunit_price_idx on fareunit_price(distance);")
c.execute("CREATE INDEX fareunit_price_keydist_idx on fareunit_price(key,distance);")
def load_unitprices(filename,key):
    for line in open(filename):
        values = line[:-1].split(',')
        for i,v in enumerate(values):
            if v == 'NULL' or v == '':
                values[i] = None
        c.execute("INSERT INTO fareunit_price VALUES (?,?,?,?,?,?,?,?)",[key,]+values)

load_unitprices('data/ns_unitprices.csv',"NS")
load_unitprices('data/nn_unitprices.csv',"NN")
load_unitprices('data/vd_unitprices.csv',"VD")
load_unitprices('data/mll_unitprices.csv',"MLL")
load_unitprices('data/ge_unitprices.csv',"GE")

c.execute(
"""
CREATE TABLE concession (
concession TEXT,
fareunits boolean,
price_second float,
price_first float,
entrance_fee float,
min_fare integer,
calc_method TEXT,
unit_price_key TEXT
);""")
c.execute("CREATE INDEX concession_idx ON concession(concession);")
for line in open('data/prices.csv'):
    values = line[:-1].split(',')
    for i,v in enumerate(values):
        if v == 'NULL':
            values[i] = None
    c.execute("INSERT INTO concession VALUES (?,?,?,?,?,?,?,?)",values)

#SET CONCESSIONS
c.execute("ALTER TABLE distance ADD COLUMN concession TEXT")
#HRN (NS)
c.execute("UPDATE distance SET concession = 'HRN' WHERE operator = 'NS'")

#Noordelijke nevenlijnen
c.execute("""
UPDATE distance set concession  = 'NOORD' WHERE operator = 'ARR' and (from_station = 'lw' OR to_station = 'lw');""")
c.execute("""UPDATE distance set concession  = 'NOORD' WHERE operator = 'ARR' and to_station in 
(SELECT DISTINCT to_station  FROM distance WHERE operator = 'ARR' and from_station = 'lw');""")

#Vechtdallijnen Arriva
c.execute("""
UPDATE distance set concession  = 'ARR_VD' WHERE operator = 'ARR' and (from_station = 'emn' or to_station = 'emn');""")
c.execute("""UPDATE distance set concession  = 'ARR_VD' WHERE operator = 'ARR' and to_station in 
(SELECT DISTINCT to_station  FROM distance WHERE operator = 'ARR' and from_station = 'emn');""")

#Zutphen - Apeldoorn Arriva
c.execute("""
UPDATE distance set concession  = 'ARR_ZP_APD' WHERE operator = 'ARR' and (from_station = 'apd' or to_station = 'apd');""")
c.execute("""UPDATE distance set concession  = 'ARR_ZP_APD' WHERE operator = 'ARR' and to_station in 
(SELECT DISTINCT to_station  FROM distance WHERE operator = 'ARR' and from_station = 'apd');""")

#MLL Arriva
c.execute("""
UPDATE distance set concession  = 'ARR_MLL' WHERE operator = 'ARR' and (from_station = 'ddr' or to_station = 'ddr');""")
c.execute("""UPDATE distance set concession  = 'ARR_MLL' WHERE operator = 'ARR' and to_station in 
(SELECT DISTINCT to_station  FROM distance WHERE operator = 'ARR' and from_station = 'ddr');""")

#Breng
c.execute("""UPDATE distance set concession  = 'BRENG' WHERE operator = 'BRENG';""")

#Limburg Zuid (Maastricht - Kerkrade)
c.execute("""
UPDATE distance set concession  = 'LIM_ZUID' WHERE operator = 'VTN' and (from_station = 'mt' or to_station = 'mt');""")
c.execute("""UPDATE distance set concession  = 'LIM_ZUID' WHERE operator = 'VTN' and to_station in 
(SELECT DISTINCT to_station  FROM distance WHERE operator = 'VTN' and from_station = 'mt');""")

#Limburg Noord (Roermond - Nijmegen)
c.execute("""
UPDATE distance set concession  = 'LIM_NOORD' WHERE operator = 'VTN' and (from_station = 'rm' or to_station = 'rm');""")
c.execute("""UPDATE distance set concession  = 'LIM_NOORD' WHERE operator = 'VTN' and to_station in 
(SELECT DISTINCT to_station  FROM distance WHERE operator = 'VTN' and from_station = 'rm');""")

c.execute("""UPDATE distance set min_distance = 6 WHERE concession like 'LIM_%';""")

#Valleilijn
c.execute("""
UPDATE distance set concession  = 'VALLEI' WHERE operator = 'CXX' and (from_station = 'bnc' or to_station = 'bnc');""")
c.execute("""UPDATE distance set concession  = 'VALLEI' WHERE operator = 'CXX' and to_station in 
(SELECT DISTINCT to_station  FROM distance WHERE operator = 'CXX' and from_station = 'bnc');""")
c.execute("""UPDATE distance set min_distance = 8 WHERE concession = 'VALLEI';""")

#Syntus ZOH
c.execute("""
UPDATE distance set concession  = 'SYNTUS_ZOH' WHERE operator = 'SYNTUS' AND (to_station = 'hgl' OR from_station = 'hgl');""")
c.execute("""UPDATE distance set concession  = 'SYNTUS_ZOH' WHERE operator = 'SYNTUS' and to_station in 
(SELECT DISTINCT to_station  FROM distance WHERE operator = 'SYNTUS' and from_station = 'hgl');""")


db.commit()
c.close()

"""DUMP
echo ".mode csv
select * from distance;" | sqlite3 data.db > distance.csv
"""
