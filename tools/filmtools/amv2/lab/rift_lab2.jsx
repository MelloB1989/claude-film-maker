var W=1920,H=1080;
function fxAdd(l, mn, label){ var e=l.property("ADBE Effect Parade").addProperty(mn); if(label){e.name=label; return l.property("ADBE Effect Parade").property(label);} return e; }
function setp(fx,n,v){ try{ fx.property(n).setValue(v);}catch(e){ $.writeln("ERR "+n+" "+e);} }
var variants=[[2,0,0],[2,1,0],[2,1,1],[1,1,1]];   // polar type, twirl first?, tri
for (var vi=0; vi<variants.length; vi++){
  var V=variants[vi];
  var c=app.project.items.addComp("V"+vi,W,H,1,1,30);
  var sw=c.layers.addSolid([0.5,0.5,0.5],"swirl",W,H,1,1);
  var fn=fxAdd(sw,"ADBE Fractal Noise","noise"); setp(fn,"Contrast",190); setp(fn,"Brightness",-15); setp(fn,"Complexity",6);
  try{ fn.property("Transform").property("Scale").setValue(60);}catch(e){}
  if (V[1]){ var tw=fxAdd(sw,"ADBE Twirl","twirl"); setp(tw,"Twirl Radius",100); setp(tw,"Angle",160); }
  var pl=fxAdd(sw,"ADBE Polar Coordinates","polar"); setp(pl,"Interpolation",100); setp(pl,"Type of Conversion",V[0]);
  var tb=fxAdd(sw,"ADBE Turbulent Displace","tear"); setp(tb,"Amount",90); setp(tb,"Size",100);
  var tt=fxAdd(sw,"ADBE Tritone","tri"); setp(tt,"Highlights",[0.75,1,1]); setp(tt,"Midtones",[0.95,0.12,0.62]); setp(tt,"Shadows",[0.06,0,0.22]);
}
app.project.save(new File("out/lab/rift_lab2.ecproj"));
