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
  # The screen changes during the boot: first the firmware's framebuffer (on
  # the Pi 5 at 1920x1080, which the panel scales down), then the real display
  # driver at the panel's own 1024x600. So the graphic is placed again on every
  # refresh, and sized relative to a 1024 wide screen: it looks the same on both.
  logo = Image("logo.png");
  sprite = Sprite();
  placed_for = 0;
  fun place() {
    width = Window.GetWidth();
    if (width != global.placed_for) {
      global.placed_for = width;
      factor = width / 1024;
      scaled = global.logo.Scale(Math.Int(global.logo.GetWidth() * factor), Math.Int(global.logo.GetHeight() * factor));
      global.sprite.SetImage(scaled);
      global.sprite.SetX(Window.GetX() + width / 2 - scaled.GetWidth() / 2);
      global.sprite.SetY(Window.GetY() + Window.GetHeight() / 2 - scaled.GetHeight() / 2);
    }
  }
  Plymouth.SetRefreshFunction(place);
  place();
  EOT
''
