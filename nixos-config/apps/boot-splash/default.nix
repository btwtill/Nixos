{ pkgs ? import <nixpkgs> {}
, text ? "NIXOS"
, background ? "1E1E1E"      # the HMI's wallpaper colour, so the handover to the desktop doesn't flash
, foreground ? "DADADA"
}:

# Boot splash: a Plymouth theme "homy" that shows one centred graphic on a plain
# background while the system starts. For now the graphic is just the text,
# rendered here; to use a real logo, replace logo.png with it.
let
  rgb = hex: builtins.concatStringsSep ", " (map (i:
    toString ((pkgs.lib.fromHexString (builtins.substring i 2 hex)) / 255.0)) [ 0 2 4 ]);
in
pkgs.runCommand "homy-boot-splash" { nativeBuildInputs = [ pkgs.imagemagick ]; } ''
  theme=$out/share/plymouth/themes/homy
  mkdir -p $theme
  magick -background none -fill '#${foreground}' \
    -font ${pkgs.dejavu_fonts}/share/fonts/truetype/DejaVuSans-Bold.ttf \
    -pointsize 64 -kerning 14 label:'${text}' $theme/logo.png

  cat > $theme/homy.plymouth <<EOT
  [Plymouth Theme]
  Name=Homy
  Description=One centred graphic on a plain background
  ModuleName=script

  [script]
  ImageDir=$theme
  ScriptFile=$theme/homy.script
  EOT

  cat > $theme/homy.script <<EOT
  Window.SetBackgroundTopColor(${rgb background});
  Window.SetBackgroundBottomColor(${rgb background});
  logo = Image("logo.png");
  sprite = Sprite(logo);
  sprite.SetX(Window.GetX() + Window.GetWidth() / 2 - logo.GetWidth() / 2);
  sprite.SetY(Window.GetY() + Window.GetHeight() / 2 - logo.GetHeight() / 2);
  EOT
''
