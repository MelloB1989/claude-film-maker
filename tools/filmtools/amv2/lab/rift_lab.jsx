// lab: the rift swirl built stage by stage, one comp per stage
var W=1920,H=1080;
function fxAdd(l, mn, label){ var e=l.property("ADBE Effect Parade").addProperty(mn); if(label){e.name=label; return l.property("ADBE Effect Parade").property(label);} return e; }
function setp(fx,n,v){ try{ fx.property(n).setValue(v);}catch(e){ $.writeln("ERR "+n+" "+e);} }
var stages=["noise","twirl","polar","turb","tri"];
for (var si=0; si<stages.length; si++){
  var c=app.project.items.addComp("L_"+stages[si],W,H,1,1,30);
  var sw=c.layers.addSolid([0.5,0.5,0.5],"swirl",W,H,1,1);
  var fn=fxAdd(sw,"ADBE Fractal Noise","noise"); setp(fn,"Contrast",190); setp(fn,"Brightness",-15); setp(fn,"Complexity",6);
  // inspect sub props
  if (si==0){ var ps=[]; for (var j=1;j<=fn.numProperties;j++) ps.push(fn.property(j).name); $.writeln("FN: "+ps.join(", ")); try{var tr=fn.property("Transform"); var q=[]; for (var k=1;k<=tr.numProperties;k++) q.push(tr.property(k).name+"="+tr.property(k).value); $.writeln("TR: "+q.join(", "));}catch(e){} }
  if (si>=1){ var tw=fxAdd(sw,"ADBE Twirl","twirl"); setp(tw,"Twirl Radius",1400); setp(tw,"Angle",300); setp(tw,"Twirl Center",[W/2,H/2]); if(si==1){var ps2=[]; for (j=1;j<=tw.numProperties;j++) ps2.push(tw.property(j).name+"="+tw.property(j).value); $.writeln("TW: "+ps2.join(", "));} }
  if (si>=2){ var pl=fxAdd(sw,"ADBE Polar Coordinates","polar"); setp(pl,"Interpolation",100); setp(pl,"Type of Conversion",1); }
  if (si>=3){ var tb=fxAdd(sw,"ADBE Turbulent Displace","tear"); setp(tb,"Amount",140); setp(tb,"Size",120); }
  if (si>=4){ var tt=fxAdd(sw,"ADBE Tritone","tri"); setp(tt,"Highlights",[0.75,1,1]); setp(tt,"Midtones",[0.95,0.12,0.62]); setp(tt,"Shadows",[0.06,0,0.22]); var ps3=[]; for (j=1;j<=tt.numProperties;j++) ps3.push(tt.property(j).name); $.writeln("TT: "+ps3.join(", ")); }
}
app.project.save(new File("out/lab/rift_lab.ecproj"));
