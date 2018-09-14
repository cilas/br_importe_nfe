# -*- coding: utf-8 -*-

from odoo import models, fields, api
class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    nfe_num = fields.Integer('Num. NFe')
    nfe_serie = fields.Char('Série')
    nfe_modelo = fields.Char('Modelo')
    nfe_chave = fields.Char('Chave NFe')
    nfe_emissao = fields.Date('Data Emissão NFe')
