import sys
data=open(sys.argv[1],'rb').read()
for s in sys.argv[2:]:
    u8=data.count(s.encode()); u16=data.count(s.encode('utf-16-le'))
    print(f"{s}: utf8={u8} utf16={u16}")
