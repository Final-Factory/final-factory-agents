import zipfile,struct,sys
def meta(path):
    b=zipfile.ZipFile(path).read('MetaSaveState2.dat')
    ver,=struct.unpack_from('<i',b,0); fp,=struct.unpack_from('<q',b,4); st,=struct.unpack_from('<q',b,12); o=20
    has=b[o]; o+=1; v=None
    if has:
        n=0;sh=0
        while True:
            c=b[o]; o+=1; n|=(c&0x7f)<<sh; sh+=7
            if c<0x80: break
        v=b[o:o+n].decode(); o+=n
    locked=b[o]
    return dict(formatVersion=ver, elapsedGameSeconds=round(fp/2**32,1), version=v, AchievementsLocked=bool(locked), rawLockedByte=locked)
for p in sys.argv[1:]: print(p.split('/')[-1], meta(p))
