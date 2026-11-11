import tests
from unittest import TestCase
from failure_catalog import default_selection
from warehouse import WarehouseItem
from technician_sat import reviewed_sat_plans, TECHNICIAN_SAT_LABEL


class TechnicianSatPlanTests(TestCase):
    def values(self):
        return {'1': {'duration': '0,75', 'incident': '12345678', 'reason': 'Motivo de prueba local'}}

    def test_review_freezes_inputs_and_keeps_technician_action_distinct(self):
        values=self.values();selection=default_selection()
        plan,=reviewed_sat_plans([WarehouseItem('1')],values,selection)
        values['1']['incident']='999';selection.clear()
        self.assertEqual(plan.incident_summary,'inc: 12345678')
        self.assertTrue(plan.anomaly_selection)
        self.assertEqual(TECHNICIAN_SAT_LABEL,'Enviar a SAT Externo')
        self.assertNotIn('Confirmar',TECHNICIAN_SAT_LABEL)

    def test_incident_and_reason_are_required_per_ot(self):
        for field in ('incident','reason'):
            values=self.values();values['1'][field]=''
            with self.subTest(field=field),self.assertRaises(ValueError):
                reviewed_sat_plans([WarehouseItem('1')],values,default_selection())

    def test_duration_requires_quarter_hours(self):
        for value in ('','0','0,1','-1','NaN'):
            values=self.values();values['1']['duration']=value
            with self.subTest(value=value),self.assertRaises(ValueError):
                reviewed_sat_plans([WarehouseItem('1')],values,default_selection())

    def test_every_ot_must_have_its_own_reviewed_values(self):
        with self.assertRaises(ValueError):
            reviewed_sat_plans([WarehouseItem('1'),WarehouseItem('2')],self.values(),default_selection())

    def test_invalid_anomaly_route_is_rejected_before_any_operation(self):
        with self.assertRaises(ValueError):
            reviewed_sat_plans([WarehouseItem('1')],self.values(),{})
