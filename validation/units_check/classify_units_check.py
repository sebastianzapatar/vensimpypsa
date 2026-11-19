import re,collections,sys
t=open(sys.argv[1],encoding='latin-1').read()
blocks=[b for b in t.split('*'*47) if b.strip()]
cat=collections.Counter(); names=collections.defaultdict(set)
for b in blocks:
    if 'No units specified' in b:
        c='missing'; n=b.split('-',1)[1].strip()
    else:
        m=re.search(r'following equation:\s*\n(.+?)(\[| =)',b); n=m.group(1).strip().lstrip('#') if m else '?'
        an=b.split('Analysis of units error:')[-1]
        if re.search(r'Months',an): c='Month/Months'
        elif 'ALLOCATE BY PRIORITY' in an: c='priority dimensionless'
        elif re.search(r'\bMWh\b',an) and re.search(r'\bMW\b',an) and 'GW' not in an: c='MW vs MWh'
        elif '/ 1000' in b or '* 1000' in b or '1e+06' in b or '* 30' in b or '800000' in b or 'MWh por GWh' in b or '* 24' in b: c='conversion constant'
        else: c='other'
    cat[c]+=1; names[c].add(n.split('[')[0])
print(len(blocks)); 
for c,v in cat.most_common(): print(f'{c:25s}{v:4d} eq, {len(names[c]):3d} vars')
print('\nOTHER vars:', sorted(names['other']))
rate={'Decided Generation Investment by Tech','Executed Interconnection Capacity','Executed Interconnection km','Executed Planned Generation','GET Used for Congestion','Available GET Capacity','Grid Technology Need','New BESS capacity','New Generation Expansion by Tech','New Generation Sum','New Need of Transmission for Demand','New Operating Capacity','New PV DER Capacity','New Transmission for Generation by Zone','Planned DER Start','Planned Generation Sum','Total GET Capacity Used','Total New Investment','Zones to Expand Interconnection Congested','Generation by Tech per Month','Spillovers','HydroDam Generation'}
real={'Generation Capacity Cost by Tech'}
sub=collections.Counter(); subv=collections.defaultdict(set)
for b in blocks:
    if 'No units specified' in b: continue
    m=re.search(r'following equation:\s*\n(.+?)(\[| =)',b); n=m.group(1).strip().split('[')[0] if m else '?'
    if n in names['other']:
        k='rate/stock' if n in rate else 'real' if n in real else 'declared wrong'
        sub[k]+=1; subv[k].add(n)
print({k:(v,len(subv[k])) for k,v in sub.items()})
