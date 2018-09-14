import base64

from lxml import objectify
from dateutil import parser
from random import SystemRandom
from datetime import datetime

from odoo import api, models, fields
from odoo.exceptions import UserError


class NotFoundProduct(models.Model):
    _name = 'not.found.products'

    product_id = fields.Many2one('product.product', string="Produto do Odoo")
    name = fields.Char(string="Produto da NFe")
    sequence = fields.Integer(string="Sequencia", default=10)


class FoundProduct(models.Model):
    _name = 'found.products'

    name = fields.Char(string="Produto da NFe")
    sequence = fields.Integer(string="Sequencia", default=10)



class WizardImportNfe(models.TransientModel):
    _name = 'wizard.import.nfe'

    nfe_xml = fields.Binary(u'XML da NFe')
    purchase_id = fields.Many2one('purchase.order',
                                  string='Pedido')
    fiscal_position_id = fields.Many2one('account.fiscal.position',
                                         string='Posição Fiscal')
    payment_term_id = fields.Many2one('account.payment.term',
                                      string='Forma de Pagamento')
    not_found_product = fields.Many2many('not.found.products', string="Produtos não encontrados")
    found_product = fields.Many2many('found.products', string="Produtos encontrados")
    confirma = fields.Boolean(string='Confirmar')
    altera = fields.Boolean(string='Alterar')
    order_line = fields.Many2many('purchase.order.line', string="Ordem dos produtos")