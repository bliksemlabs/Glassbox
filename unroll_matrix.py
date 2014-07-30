import sys

f = open(sys.argv[1],'r')
g = open('unrolled'+sys.argv[1],'w')
header = f.readline()[:-1].split(',')
for line in f:
    v = line[:-1].split(',')
    from_station = v[0]
    for i,fare in enumerate(v[1:]):
        to_station = header[i+1]
        if to_station == from_station: continue
        try:
            x = int(fare)
        except:
            continue
        g.write(','.join([from_station,to_station,fare,sys.argv[2]])+'\n')
g.close()
