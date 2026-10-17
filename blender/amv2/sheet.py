import sys,glob
from PIL import Image,ImageDraw
d,out,cols=sys.argv[1],sys.argv[2],int(sys.argv[3])
fs=sorted(glob.glob(d+"/0*.png"))
ims=[Image.open(f) for f in fs]
w,h=ims[0].size
rows=(len(ims)+cols-1)//cols
S=Image.new('RGB',(cols*w,rows*h))
for i,(f,im) in enumerate(zip(fs,ims)):
    ImageDraw.Draw(im).text((4,4),f[-8:-4],fill=(255,255,0))
    S.paste(im,((i%cols)*w,(i//cols)*h))
S.convert("RGB").save(out,quality=88)
print(w,h,len(ims))
