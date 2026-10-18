"""Build an offline, byte-for-byte repeatable VSIX with Python's standard library."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile
from xml.sax.saxutils import escape


HERE = Path(__file__).resolve().parent
FILES = ('README.md', 'language-configuration.json', 'package.json', 'syntaxes/dong.tmLanguage.json')


def payloads():
    package = json.loads((HERE / 'package.json').read_text(encoding='utf-8'))
    publisher, name, version = (escape(package[k], {'"': '&quot;'})
                                for k in ('publisher', 'name', 'version'))
    description = escape(package['description'])
    engine = escape(package['engines']['vscode'], {'"': '&quot;'})
    types = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="json" ContentType="application/json"/>'
             '<Default Extension="md" ContentType="text/markdown"/>'
             '<Default Extension="vsixmanifest" ContentType="text/xml"/>'
             '</Types>\n')
    manifest = f'''<?xml version="1.0" encoding="UTF-8"?>
<PackageManifest Version="2.0.0" xmlns="http://schemas.microsoft.com/developer/vsx-schema/2011">
  <Metadata>
    <Identity Language="en-US" Id="{name}" Version="{version}" Publisher="{publisher}"/>
    <DisplayName>{escape(package['displayName'])}</DisplayName>
    <Description xml:space="preserve">{description}</Description>
    <Tags>dong,.dg,language</Tags><Categories>Programming Languages</Categories>
    <GalleryFlags>Public</GalleryFlags>
    <Properties><Property Id="Microsoft.VisualStudio.Code.Engine" Value="{engine}"/></Properties>
  </Metadata>
  <Installation><InstallationTarget Id="Microsoft.VisualStudio.Code"/></Installation>
  <Dependencies/>
  <Assets>
    <Asset Type="Microsoft.VisualStudio.Code.Manifest" Path="extension/package.json" Addressable="true"/>
    <Asset Type="Microsoft.VisualStudio.Services.Content.Details" Path="extension/README.md" Addressable="true"/>
  </Assets>
</PackageManifest>
'''
    result = {'[Content_Types].xml': types.encode('utf-8'), 'extension.vsixmanifest': manifest.encode('utf-8')}
    result.update({'extension/' + p: (HERE / p).read_bytes() for p in FILES})
    return result


def build(destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(payloads().items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, data)
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=HERE / 'dist/dong-language-0.1.0.vsix')
    args = parser.parse_args()
    digest = build(args.output)
    print(f'{digest}  {args.output.resolve()}')


if __name__ == '__main__':
    main()
