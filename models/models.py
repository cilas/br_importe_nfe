# -*- coding: utf-8 -*-
from odoo import models, fields
from odoo.addons import decimal_precision as dp


class AccountInvoice(models.Model):
    _inherit = 'account.invoice'

    nfe_num = fields.Integer('Num. NFe')
    nfe_serie = fields.Char('Série')
    nfe_modelo = fields.Char('Modelo')
    nfe_chave = fields.Char('Chave NFe')
    nfe_emissao = fields.Date('Data Emissão NFe')


class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    nfe_num = fields.Integer('Num. NFe')
    nfe_serie = fields.Char('Série')
    nfe_modelo = fields.Char('Modelo')
    nfe_chave = fields.Char('Chave NFe')
    nfe_emissao = fields.Date('Data Emissão NFe')


class ResPartner(models.Model):
    _inherit = 'res.partner'

    indicador_ie_dest = fields.Selection(
        [('1', u'1 - Contribuinte ICMS'),
         ('2', u'2 - Contribuinte isento de Inscrição no cadastro de \
                Contribuintes do ICMS'),
         ('9', u'9 - Não Contribuinte, que pode ou não possuir Inscrição \
                Estadual no Cadastro de Contribuintes do ICMS')],
        string="Indicador IE", help=u"Caso não preencher este campo vai usar a \
        regra:\n9 - para pessoa física\n1 - para pessoa jurídica com IE \
        cadastrada\n2 - para pessoa jurídica sem IE cadastrada ou 9 \
        caso o estado de destino for AM, BA, CE, GO, MG, MS, MT, PE, RN, SP"
    )


class FatorConversao(models.Model):
    _name = 'fator.conversao'

    name = fields.Char(
        string="Nome do fator",
        required=True
    )
    tipo = fields.Selection(
        [
            ('0', u"Multiplicar"),
            ('1', u"Dividir")
        ],
        string=u'Tipo de fator',
        required=True
    )

    valor = fields.Float(
        string=u'Valor do fator',
        required=True,
        digits=dp.get_precision('Product Unit of Measure')
    )