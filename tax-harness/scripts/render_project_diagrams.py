"""通过已安装Edge把SVG导出PNG供预览；不修改SVG或业务数据。"""
import json
from pathlib import Path
import tempfile
from xml.etree import ElementTree
from browser_driver import Browser

ROOT=Path(__file__).resolve().parents[1]


def main():
    folder=ROOT/'docs/understanding/figures'
    files=[folder/name for name in ['architecture.svg','query-chain.svg','save-chain.svg']]
    with tempfile.TemporaryDirectory(prefix='test-diagrams-',dir=ROOT/'data') as temp:
        browser=Browser(files[0].resolve().as_uri(),Path(temp)/'edge-profile')
        try:
            for index,path in enumerate(files):
                root=ElementTree.parse(path).getroot()
                title=root.find('{http://www.w3.org/2000/svg}title').text
                if index:browser.call('Page.navigate',{'url':path.resolve().as_uri()})
                browser.wait("document.querySelector('title') && document.querySelector('title').textContent==="+json.dumps(title))
                browser.call('Emulation.setDeviceMetricsOverride',{'width':int(root.attrib['width']),'height':int(root.attrib['height']),'deviceScaleFactor':1,'mobile':False})
                browser.screenshot(path.with_suffix('.png'))
                print(path.with_suffix('.png'))
        finally:browser.close()


if __name__=='__main__':main()
