import os,json,uuid,shutil
from pathlib import Path
from urllib.request import urlopen,Request
from urllib.error import HTTPError
from lxml import etree
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
root=Path(__file__).resolve().parents[1]
manifest=etree.parse(str(root/'manifest.xml'));ns={'m':'http://schemas.microsoft.com/office/appforoffice/1.1','bt':'http://schemas.microsoft.com/office/officeappbasictypes/1.0','v':'http://schemas.microsoft.com/office/mailappversionoverrides/1.1'}
assert manifest.find('m:Permissions',ns).text=='ReadItem'
assert manifest.xpath('count(//v:SupportsPinning)',namespaces=ns)==1
for url in manifest.xpath('//@DefaultValue'):
 if url.startswith('https://localhost:3000'):
  path=url.removeprefix('https://localhost:3000')
  assert urlopen('http://127.0.0.1:3001'+path).status==200,path
for path in ['/.local/password.txt','/../server.mjs','/core.mjs/../../server.mjs']:
 try:urlopen('http://127.0.0.1:3001'+path);raise AssertionError(path)
 except HTTPError as exc:assert exc.code==404
try:urlopen(Request('http://127.0.0.1:3001/taskpane.html',data=b'private-mail'));raise AssertionError('POST accepted')
except HTTPError as exc:assert exc.code==405
print('MANIFEST_ASSETS_AND_SERVER_OK',flush=True)
profile=Path(__file__).parent/('outlook-ui-'+uuid.uuid4().hex);profile.mkdir()
options=Options();options.add_argument('--headless=new');options.add_argument('--disable-gpu');options.add_argument('--user-data-dir='+str(profile));options.add_argument('--window-size=440,1000')
driver=None
try:
 driver=webdriver.Edge(options=options);driver.get('http://localhost:3001/taskpane.html?demo=1')
 wait=WebDriverWait(driver,15);wait.until(lambda d:d.find_element(By.ID,'ot').get_attribute('value')=='4448382')
 assert driver.find_element(By.ID,'md').get_attribute('href')=='maximodesk://ot/4448382'
 driver.find_element(By.CSS_SELECTOR,'summary').click()
 driver.find_element(By.ID,'development').click();assert driver.find_element(By.ID,'md').get_attribute('href')=='maximodesk-dev://ot/4448382'
 driver.execute_script("document.getElementById('sample').value='OT 4448382\\nOT 4446909';document.getElementById('parse-demo').click()")
 assert driver.find_element(By.ID,'ot').get_attribute('value')==''
 assert driver.find_element(By.ID,'web').get_attribute('href') is None
 driver.execute_script("const s=document.getElementById('candidates');s.value='4446909';s.dispatchEvent(new Event('change'))")
 assert driver.find_element(By.ID,'ot').get_attribute('value')=='4446909'
 driver.execute_script("document.getElementById('sample').value='<p>La orden de trabajo: &quot;4448382 &quot;</p><script>OT 9999999</scr'+'ipt>';document.getElementById('parse-demo').click()")
 assert driver.find_element(By.ID,'ot').get_attribute('value')=='4448382'
 # Exercise the same Outlook callbacks with an out-of-order response, no mailbox needed.
 driver.execute_script("""window.callbacks=[];window.Office={CoercionType:{Html:'html'},AsyncResultStatus:{Succeeded:'ok'},context:{mailbox:{item:null}}};
 const mk=id=>({subject:'Aviso',body:{getAsync:(_,callback)=>callbacks.push(callback)}});
 Office.context.mailbox.item=mk('A');document.getElementById('refresh').click();
 Office.context.mailbox.item=mk('B');document.getElementById('refresh').click();
 callbacks[1]({status:'ok',value:'OT 4446909'});callbacks[0]({status:'ok',value:'OT 4448382'});""")
 assert driver.find_element(By.ID,'ot').get_attribute('value')=='4446909'
 driver.execute_script("document.getElementById('refresh').click();const i=document.getElementById('ot');i.value='4448382';i.dispatchEvent(new Event('input'));callbacks[2]({status:'ok',value:'OT 4446909'})")
 assert driver.find_element(By.ID,'ot').get_attribute('value')=='4448382'
 driver.execute_script("document.getElementById('ot').value=arguments[0];document.getElementById('ot').dispatchEvent(new Event('input'))", "4448382' or 1=1")
 assert driver.find_element(By.ID,'md').get_attribute('href') is None
 driver.get('http://localhost:3001/launch.html?ot=4448382')
 wait.until(lambda d:d.find_element(By.ID,'launch').get_attribute('href')=='maximodesk://ot/4448382')
 driver.get('http://localhost:3001/taskpane.html?demo=1')
 wait.until(lambda d:d.find_element(By.ID,'ot').get_attribute('value')=='4448382')
 # No mailbox contents or screenshots are retained by this test.
 assert driver.execute_script('return document.documentElement.scrollWidth <= innerWidth')
 print('BROWSER_DETECTION_MULTIPLE_OT_RACES_MANUAL_EDITS_AND_BRIDGE_OK',flush=True)
finally:
 if driver:driver.quit()
 if profile.exists():shutil.rmtree(profile)
