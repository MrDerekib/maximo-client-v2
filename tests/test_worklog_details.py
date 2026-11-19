import tests
from unittest import TestCase
from unittest.mock import Mock,call
from selenium.webdriver.common.keys import Keys
from technician_repair import RepairPreparer
from worklog_details import details_match

class WorklogDetailsTests(TestCase):
    def test_browser_spacing_is_equivalent_but_words_and_line_order_are_not(self):
        expected='Cliente\t0000\r\nCPU\t\r\n\t\r\nImpresora\tSUSTITUCIÓN\r\nNotas:\tPrueba correcta\u2003'
        rendered='Cliente 0000\nCPU\xa0\n\t\nImpresora SUSTITUCIÓN\nNotas: Prueba correcta'
        self.assertTrue(details_match(expected,rendered))
        self.assertFalse(details_match(expected,rendered.replace('SUSTITUCIÓN','')))
        self.assertFalse(details_match(expected,rendered.replace('Impresora SUSTITUCIÓN','SUSTITUCIÓN Impresora')))
        self.assertFalse(details_match(expected,rendered.replace('\nCPU',' CPU')))
        self.assertFalse(details_match(expected,rendered.replace('\n\t\n','\n')))

    def preparer(self, actual):
        driver=Mock();frame=Mock();frame.is_displayed.return_value=True
        body=Mock();body.text=actual;body.get_property.return_value=actual
        driver.find_elements.return_value=[frame];driver.find_element.return_value=body
        preparer=RepairPreparer(driver,'1','INPRG')
        preparer.response_sequence=Mock(return_value=1);preparer.wait=Mock();preparer.require_approved=Mock()
        return preparer,driver,body

    def test_excel_text_is_inserted_once_without_typing_its_tabs(self):
        text='Cliente\t0000\nCPU\tPREVENTIVO\nNotas:\tPrueba completa'
        p,driver,body=self.preparer(text.replace('\t',' '))
        p.details(text)
        driver.execute_cdp_cmd.assert_called_once_with('Input.insertText',{'text':text})
        self.assertEqual(body.send_keys.call_args_list,[call(Keys.CONTROL,'a'),call(Keys.TAB)])
        driver.switch_to.default_content.assert_called_once()
        p.wait.assert_called_once();p.require_approved.assert_called_once()

    def test_missing_text_stops_before_validation_and_never_replays(self):
        p,driver,body=self.preparer('CPU')
        with self.assertRaisesRegex(RuntimeError,'todos los detalles'):p.details('CPU\tPREVENTIVO')
        driver.execute_cdp_cmd.assert_called_once()
        self.assertEqual(body.send_keys.call_args_list,[call(Keys.CONTROL,'a')])
        driver.switch_to.default_content.assert_called_once();p.require_approved.assert_not_called()

    def test_failed_native_insertion_does_not_fall_back_to_keyboard_typing(self):
        p,driver,body=self.preparer('')
        driver.execute_cdp_cmd.side_effect=RuntimeError('insertion uncertain')
        with self.assertRaisesRegex(RuntimeError,'uncertain'):p.details('CPU\tPREVENTIVO')
        driver.execute_cdp_cmd.assert_called_once()
        self.assertEqual(body.send_keys.call_args_list,[call(Keys.CONTROL,'a')])
        driver.switch_to.default_content.assert_called_once()

    def test_reading_details_never_inserts_or_validates(self):
        p,driver,body=self.preparer('Existing content')
        self.assertEqual(p.details(),'Existing content')
        driver.execute_cdp_cmd.assert_not_called();body.send_keys.assert_not_called()
