"""Offline browser integration of the panel, never installed profiles or Maximo."""
import tests
import os
import unittest
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from workorder_close import BROWSER_BUTTON_SCRIPT
from maximo_client import start_repair_report

EXTENSION=Path(__file__).resolve().parents[1]/'browser_extension'
LOCATION="const location={origin:'https://eam.indraweb.net',pathname:'/maximo/ui/',href:'https://eam.indraweb.net/maximo/ui/'};"

@unittest.skipUnless(os.environ.get('MAXIMO_BROWSER_TESTS')=='1','Offline Edge tests are opt-in')
class ExtensionPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        options=Options();options.add_argument('--headless=new')
        cls.browser=webdriver.Edge(options=options)
    @classmethod
    def tearDownClass(cls):cls.browser.quit()

    def test_hidden_close_adapter_opens_review_request_without_routing(self):
        fixture=Path(__file__).parent/'fixtures/workorder_close.html'
        self.browser.get(fixture.resolve().as_uri())
        self.browser.execute_script(LOCATION+BROWSER_BUTTON_SCRIPT)
        self.browser.execute_script("document.documentElement.dataset.maximoPresentation='sidepanel';const s=document.createElement('style');s.textContent=arguments[0];document.head.append(s)",
                                    (EXTENSION/'panel_content.css').read_text())
        self.assertFalse(self.browser.find_element(By.ID,'maximo-desktop-close-ot').is_displayed())
        bridge=(EXTENSION/'panel_bridge.js').read_text()
        snapshot=self.browser.execute_script(LOCATION+bridge+';return maximoPanelBridge({});')
        self.assertEqual(snapshot['status'],'INPRG')
        self.assertEqual([item['key'] for item in snapshot['actions']],['close'])
        self.browser.execute_script(LOCATION+bridge+';return maximoPanelBridge(arguments[0]);',
                                    {'action':'close','ot':'4378677','status':'INPRG'})
        state=self.browser.execute_script('return {request:JSON.parse(document.documentElement.dataset.maximoCloseOtRequest),routes:state.routes};')
        self.assertEqual(state['request']['action'],'prepare')
        self.assertEqual(state['routes'],0)

    def test_close_crosses_js_worlds_without_exposing_md_globals(self):
        fixture=Path(__file__).parent/'fixtures/workorder_close.html'
        self.browser.get(fixture.resolve().as_uri())
        frame=self.browser.execute_cdp_cmd('Page.getFrameTree',{})['frameTree']['frame']['id']
        context=self.browser.execute_cdp_cmd('Page.createIsolatedWorld',{'frameId':frame,'worldName':'MD-offline-test'})['executionContextId']
        result=self.browser.execute_cdp_cmd('Runtime.evaluate',{'contextId':context,
            'expression':'(function(){'+LOCATION+BROWSER_BUTTON_SCRIPT+'})()','returnByValue':True})
        self.assertNotIn('exceptionDetails',result)
        self.assertEqual(self.browser.execute_script('return typeof globalThis.MaximoDesktopRequestClose'),'undefined')
        bridge=(EXTENSION/'panel_bridge.js').read_text()
        result=self.browser.execute_script(LOCATION+bridge+';return maximoPanelBridge(arguments[0]);',
                                          {'action':'close','ot':'4378677','status':'INPRG'})
        self.assertNotIn('panelError',result)
        self.assertEqual(self.browser.execute_script('return JSON.parse(document.documentElement.dataset.maximoCloseOtRequest).action'),'prepare')
        self.assertEqual(self.browser.execute_script('return state.routes'),0)

    def test_desktop_print_still_invokes_hidden_adapter(self):
        self.browser.get((EXTENSION/'sidepanel.html').resolve().as_uri())
        self.browser.execute_script("""
          document.body.innerHTML='<label for="mx45-tb">Orden de trabajo:</label><input id="mx45-tb" value="4378677"><label for="mx73-tb">Estado:</label><input id="mx73-tb" value="ISSUE">';
          window.sent=[];window.chrome={runtime:{onMessage:{addListener(){}},async sendMessage(message){window.sent.push(message);return {ok:false,error:'Offline: stop before report generation'};}}};
          document.documentElement.dataset.maximoPresentation='sidepanel';
          const style=document.createElement('style');style.textContent=arguments[0];document.head.append(style);
        """,(EXTENSION/'panel_content.css').read_text())
        self.browser.execute_script((EXTENSION/'workflow_logic.js').read_text())
        self.browser.execute_script(LOCATION+(EXTENSION/'content.js').read_text())
        WebDriverWait(self.browser,3).until(lambda d:d.find_elements(By.ID,'maximo-desktop-print-part'))
        self.assertFalse(self.browser.find_element(By.ID,'maximo-desktop-print-part').is_displayed())
        start_repair_report(self.browser,'4378677','pdf')
        WebDriverWait(self.browser,3).until(lambda d:d.execute_script('return sent.length'))
        sent=self.browser.execute_script('return sent')
        self.assertEqual(sent[0]['type'],'START');self.assertEqual(sent[0]['outputFormat'],'pdf')

    def test_panel_ui_tracks_state_and_disables_actions_while_busy(self):
        stub="""
          window.panelCalls=[];window.panelState={tabId:7,ot:'4400123',status:'INPRG',client:'TMB BOIXERES',progress:[],messages:[],actions:[{key:'close',label:'Cerrar OT…',group:'primary',enabled:true},{key:'change',label:'Cambiar anomalías',group:'prepare',enabled:true}]};
          window.chrome={windows:{getCurrent:async()=>({id:1})},tabs:{onActivated:{addListener(){}}},runtime:{sendMessage:async message=>{
            if(message.type==='PANEL_ACTION'){panelCalls.push(message);panelState.progress=['Revisando cierre…'];}
            return {ok:true,value:panelState};
          }}};
        """
        token=self.browser.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument',{'source':stub})['identifier']
        try:
            self.browser.get((EXTENSION/'sidepanel.html').resolve().as_uri())
            wait=WebDriverWait(self.browser,4)
            wait.until(lambda d:d.find_element(By.ID,'ot').text=='OT 4400123')
            self.browser.find_element(By.CSS_SELECTOR,'[data-action=close]').click()
            wait.until(lambda d:'Revisando' in d.find_element(By.ID,'progress').text)
            self.assertTrue(all(not button.is_enabled() for button in self.browser.find_elements(By.CSS_SELECTOR,'#actions button')))
            self.assertEqual(self.browser.execute_script('return panelCalls[0].ot'),'4400123')
            self.browser.execute_script("panelState={tabId:7,ot:'4400123',status:'ISSUE',client:'TMB BOIXERES',progress:[],messages:[],actions:[{key:'print',label:'Imprimir parte',group:'documents',enabled:true}]}")
            wait.until(lambda d:d.find_elements(By.CSS_SELECTOR,'[data-action=print]'))
            self.assertEqual(len(self.browser.find_elements(By.CSS_SELECTOR,'#actions button')),1)
            for width in (300,360,480):
                self.browser.set_window_size(width,800)
                self.assertTrue(self.browser.execute_script('return document.documentElement.scrollWidth<=innerWidth'))
        finally:self.browser.execute_cdp_cmd('Page.removeScriptToEvaluateOnNewDocument',{'identifier':token})


    def test_bundled_pdf_merger_runs_in_edge_and_preserves_page_order(self):
        self.browser.get((EXTENSION/'sidepanel.html').resolve().as_uri())
        self.browser.execute_script((EXTENSION/'vendor/pdf-lib.min.js').read_text(encoding='utf-8'))
        self.browser.execute_script((EXTENSION/'pdf_merge.js').read_text(encoding='utf-8')+';globalThis.mergeRepairPdfs=mergeRepairPdfs;globalThis.repairPdfBase64=repairPdfBase64;')
        result=self.browser.execute_async_script("""
          const done=arguments[arguments.length-1];
          (async()=>{
            const first=await PDFLib.PDFDocument.create();first.addPage([200,400]);
            const second=await PDFLib.PDFDocument.create();second.addPage([300,400]);
            const uri=await mergeRepairPdfs([repairPdfBase64(await first.save()),await second.save()]);
            const merged=await PDFLib.PDFDocument.load(uri);
            return {pdf:uri.startsWith('data:application/pdf;base64,'),widths:merged.getPages().map(p=>p.getWidth())};
          })().then(done,error=>done({error:String(error)}));
        """)
        self.assertEqual(result,{'pdf':True,'widths':[200,300]})
