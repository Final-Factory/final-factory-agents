import base64,gzip,json,sys
# usage: mkbp.py "<ItemName>" <Length(z)> <Width(x)> [Direction 0..3]
name,length,width=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]); d=int(sys.argv[4]) if len(sys.argv)>4 else 0
s=open(__import__('os').path.join(__import__('os').path.dirname(__file__),'bp_sample.txt')).read().strip()
j=json.loads(gzip.decompress(base64.b64decode(s[16:])).decode())
it=dict(j["Items"][0]); it.update({"ItemName":name,"Length":length,"Width":width,"OriginalDirection":d,
  # The sample item is a Dark Star Gate with range 0/0; a Defense Platform or Construction Tower placed from it
  # would get 0 m and never fight/build (074 T173). The game clamps a blueprint's range to the structure's own
  # config ceiling (StructureRangeResolver.Clamp), so a huge value places every ranged structure at its maximum.
  "AttackRange":1e6,"AlertRange":1e6})
j={"Name":f"single {name}","Icon":name,"Version":j["Version"],"Items":[it]}
for k in ("Length","Width"): j[k]=it[k]
print("ffblueprintstart"+base64.b64encode(gzip.compress(json.dumps(j).encode())).decode())
