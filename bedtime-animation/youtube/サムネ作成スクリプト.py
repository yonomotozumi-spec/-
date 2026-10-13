from PIL import Image, ImageDraw, ImageFont, ImageFilter
I='/home/user/-/bedtime-animation/images/'
F='/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf'
def base(name):
    im=Image.open(I+name).convert('RGB')
    w,h=im.size; r=max(1280/w,720/h); im=im.resize((int(w*r+0.5),int(h*r+0.5)),Image.LANCZOS)
    x=(im.width-1280)//2; y=(im.height-720)//2
    return im.crop((x,y,x+1280,y+720))
def shade(im,box,alpha=150,blur=30):
    ov=Image.new('L',im.size,0); d=ImageDraw.Draw(ov); d.rounded_rectangle(box,40,fill=alpha)
    ov=ov.filter(ImageFilter.GaussianBlur(blur))
    dark=Image.new('RGB',im.size,(18,24,58)); return Image.composite(dark,im,ov)
def text(d,xy,s,size,fill,stroke=(25,30,70),sw=10,anchor='la'):
    f=ImageFont.truetype(F,size); d.text(xy,s,font=f,fill=fill,stroke_width=sw,stroke_fill=stroke,anchor=anchor)
def badge(d,xy,s,size=40):
    f=ImageFont.truetype(F,size); x,y=xy; b=d.textbbox((x,y),s,font=f)
    d.rounded_rectangle((b[0]-22,b[1]-14,b[2]+22,b[3]+14),30,fill=(255,214,102)); d.text((x,y),s,font=f,fill=(40,40,90))
# 案A：大きなお月さま（カット13）＋下にタイトル
im=base('カット13_おつきさまのそば_v1.png'); im=shade(im,(60,470,1220,720),170)
d=ImageDraw.Draw(im)
text(d,(640,560),'おつきさまのこぶね',104,(255,246,214),anchor='mm')
text(d,(640,660),'どうぶつたちに おやすみを いいにいこう',44,(255,255,255),sw=6,anchor='mm')
badge(d,(40,36),'ねかしつけ アニメ',40)
im.save('サムネ案A_お月さま.jpg',quality=90)
# 案B：ふくろうとさく（カット5）＋右上にタイトル
im=base('カット05_ふくろうの木_v1.png'); im=shade(im,(560,20,1270,330),160)
d=ImageDraw.Draw(im)
text(d,(915,120),'おつきさまの',78,(255,246,214),anchor='mm')
text(d,(915,215),'こぶね',118,(255,246,214),anchor='mm')
text(d,(915,300),'ふくろうさん、おやすみ',40,(255,255,255),sw=6,anchor='mm')
badge(d,(40,640),'ねかしつけ アニメ・約5分',36)
im.save('サムネ案B_ふくろう.jpg',quality=90)
# 案C：くじらとさく（カット10）＋上にタイトル
im=base('カット10_くじらの海_v1.png'); im=shade(im,(40,10,1240,250),150)
d=ImageDraw.Draw(im)
text(d,(640,105),'おつきさまのこぶね',100,(255,246,214),anchor='mm')
text(d,(640,200),'8ひきの どうぶつに おやすみ',46,(255,255,255),sw=6,anchor='mm')
badge(d,(960,640),'ねかしつけ アニメ',36)
im.save('サムネ案C_くじら.jpg',quality=90)
import os
for f in sorted(os.listdir('.')):
    if f.endswith('.jpg'): print(f, os.path.getsize(f)//1024,'KB', Image.open(f).size)
