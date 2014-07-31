import sys

f = open(sys.argv[1],'r')
g = open('unrolled'+sys.argv[1],'w')
header = f.readline().replace('\r\n','').split(',')
stations = set([])
for line in f:
    line = line.replace('\r\n','').replace('\n','')
    v = line.split(',')
    from_station = v[0]
    for i,fare in enumerate(v[1:]):
        to_station = header[i+1]
        if to_station == from_station: continue
        try:
            x = int(fare)
        except:
            continue
        stations.add(to_station)
        stations.add(from_station)
        if len(from_station) == 0:
            print v
        if len(to_station) == 0:
            print v
        g.write(','.join([from_station,to_station,fare,sys.argv[2]])+'\n')
print stations
g.close()
