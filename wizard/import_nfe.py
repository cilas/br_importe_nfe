import base64

from lxml import objectify
from dateutil import parser
from random import SystemRandom
from datetime import datetime
import logging
from odoo import api, models, fields
from odoo.exceptions import UserError
_logger = logging.getLogger(__name__)
STATE = {'edit': [('readonly', False)]}


class WizardProdutos(models.Model):
    _name = 'wizard.produtos'

    product_id = fields.Many2one('product.product', string="Produto do Odoo")
    name = fields.Char(string="Produto da NFe")
    fator = fields.Float(string=u"Fator de conversão")
    uom_int = fields.Many2one(
        'product.uom', string=u'Unidade Medida do Estabelicmento', states=STATE)
    uom_ext = fields.Many2one(
        'product.uom', string=u'Unidade Medida do XML', states=STATE)

class WizardImportNfe(models.TransientModel):
    _name = 'wizard.import.nfe'

    nfe_xml = fields.Binary(u'XML da NFe')
    purchase_id = fields.Many2one('purchase.order',
                                  string='Pedido')
    fiscal_position_id = fields.Many2one('account.fiscal.position',
                                         string='Posição Fiscal')
    payment_term_id = fields.Many2one('account.payment.term',
                                      string='Forma de Pagamento')
    wizard_produtos = fields.Many2many('wizard.produtos', string="Produtos Nota Fiscal")
    confirma = fields.Boolean(string='Confirmar')
    altera = fields.Boolean(string='Alterar')


    @api.multi
    def action_import_nfe_purchase(self):
        if not self.nfe_xml:
            raise UserError('Por favor, insira um arquivo de NFe.')
        nfe_string = base64.b64decode(self.nfe_xml)
        nfe = objectify.fromstring(nfe_string)

        # Variaveis uteis
        items = []
        cont = 1

        # Carregando fornecedor / Criando
        partner = self.get_partner(emit=nfe.NFe.infNFe.emit)

        # Verificando se a nota ja existe no sistema
        order = self.env['purchase.order'].search([
            ('partner_id', '=', partner.id),
            ('partner_ref', '=', nfe.NFe.infNFe.ide.nNF)
        ])
        if order:
            raise UserError('Nota já importada')

        # Criando nota no sistema
        nota_dict = dict(
            partner_id=partner.id,
            date_approve=self.retorna_data(nfe.NFe.infNFe.ide.dhEmi),
            date_planned=self.retorna_data(nfe.NFe.infNFe.ide.dhEmi),
            date_order=self.retorna_data(nfe.NFe.infNFe.ide.dhEmi),
            payment_term_id=self.payment_term_id.id,
            fiscal_position_id=self.fiscal_position_id.id,
            partner_ref=nfe.NFe.infNFe.ide.nNF,
            nfe_num=nfe.NFe.infNFe.ide.nNF,
            nfe_emissao=self.retorna_data(nfe.NFe.infNFe.ide.dhEmi),
            nfe_serie=nfe.NFe.infNFe.ide.serie,
            nfe_modelo=nfe.NFe.infNFe.ide.mod,
            nfe_chave=nfe.protNFe.infProt.chNFe,
            state='purchase',
            picking_count=1,
        )
        nota = self.env['purchase.order'].create(nota_dict)

        # Criando produtos na nota
        for produto in self.wizard_produtos:
            for prod in nfe.NFe.infNFe.det:
                prod = prod.prod
                if produto.name == prod.xProd:
                    # Verificando se o produto tem fator de conversão
                    if produto.fator > 0:
                        # Aplicando fator de conversão
                        quantidade = prod.qCom * produto.fator
                        preco_unitario = prod.vProd / quantidade
                    else:
                        quantidade = prod.qCom
                        preco_unitario = prod.vUnCom

                    # Verificando se a unidade medida externa foi informada
                    if not produto.uom_ext:
                        raise UserError('A unidade medida do XML do produto: ' + produto.name + ' é obrigatoria')

                    # Verificando se o produto foi relacionado
                    if not produto.product_id:
                        # Cadastrando produto
                        produto.product_id = self.cadastro_de_produto(produto, prod, preco_unitario)

                    # Pesquisando relacionamentos do produto
                    product_code = self.env['product.supplierinfo'].search([
                        ('product_code', '=', prod.cProd.text),
                        ('name', '=', partner.id)
                    ], limit=1)

                    # Verificando se o produto ja possui algum relacionamento com o fornecedor
                    if not product_code:
                        # Cadastrando relacionamento
                        self.relacionamento_produto_fornecedor(partner, produto, prod)

                    purchase_order_line = self.env['purchase.order.line'].create({
                        'product_id': produto.product_id.id,
                        'name': prod.xProd,
                        'date_planned': self.retorna_data(nfe.NFe.infNFe.ide.dhEmi),
                        'product_qty': quantidade,
                        'price_unit': preco_unitario,
                        'product_uom': produto.uom_int.id,
                        'order_id': nota.id,
                        'partner_id': partner.id,
                        'product_qty_xml': float(quantidade),
                        'product_uom_xml': produto.uom_ext.id,
                        'num_item_xml': cont
                    })
                    cont += 1

                items.append((4, purchase_order_line.id, False))

        nota_dict = {'order_line': items}
        nota.write(nota_dict)
        nota._compute_tax_id()


    @staticmethod
    def arruma_cpf_cnpj(partner_doc):
        if len(partner_doc) > 11:
            if len(partner_doc) < 14:
                partner_doc = partner_doc.zfill(14)
            partner_doc = "%s.%s.%s/%s-%s" % (partner_doc[0:2],
                                              partner_doc[2:5],
                                              partner_doc[5:8],
                                              partner_doc[8:12],
                                              partner_doc[12:14])
        else:
            if len(partner_doc) < 11:
                partner_doc = partner_doc.zfill(11)
            partner_doc = "%s.%s.%s-%s" % (partner_doc[0:3],
                                           partner_doc[3:6],
                                           partner_doc[6:9],
                                           partner_doc[9:11])
        return partner_doc

    def cadastro_de_produto(self, produto_wizard, produto_xml, preco_unitario):
        vals = {
            'name': produto_xml.xProd.text,
            'default_code': produto_xml.cProd.text,
            'type': 'product',
            'list_price': preco_unitario,
            'purchase_method': 'receive'
        }

        if produto_wizard.uom_int:
            vals['product_uom_xml_id'] = produto_wizard.uom_int.id
        else:
            raise UserError('A unidade medida interna do produto: ' + produto_wizard.name + ' é obrigatoria')

        if hasattr(produto_xml, 'CEST'):
            vals['cest'] = produto_xml.CEST

        if hasattr(produto_xml, 'rastro'):
            vals['tracking'] = 'lot'
        else:
            vals['tracking'] = 'none'

        pf_ids = self.env['product.fiscal.classification'].search([('code', '=', produto_xml.NCM)])
        vals['fiscal_classification_id'] = pf_ids.id
        product_id = self.env['product.product'].create(vals)
        return product_id

    def relacionamento_produto_fornecedor(self, partner, produto, item):
        # cadastra o relacionamento entre fornecedor e produto
        prd_ids = {
            'product_id': produto.product_id.id,
            'product_tmpl_id': produto.product_id.product_tmpl_id.id,
            'name': partner.id,
            'product_name': item.xProd.text,
            'product_code': item.cProd.text
        }
        self.env['product.supplierinfo'].create(prd_ids)

    def checa_produtos(self):
        if not self.nfe_xml:
            raise UserError('Por favor, insira um arquivo de NFe.')
        nfe_string = base64.b64decode(self.nfe_xml)
        nfe = objectify.fromstring(nfe_string)

        items = []
        for det in nfe.NFe.infNFe.det:
            item = self.carrega_produtos(det, nfe)
            if item:
                items.append(item.id)
        self.wizard_produtos = self.env['wizard.produtos'].browse(items)
        self.confirma = True

        return {
            'context': self.env.context,
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'wizard.import.nfe',
            'res_id': self.id,
            'view_id': False,
            'type': 'ir.actions.act_window',
            'target': 'new',
        }

    def carrega_produtos(self, item, nfe):
        product_find = False
        product_create = {'name': item.prod.xProd, 'uom_int': 1}

        uom_id = self.env['product.uom'].search([
            ('name', '=', str(item.prod.uCom))], limit=1).id

        if uom_id:
            product_create['uom_ext'] = uom_id

        if item.prod.cEAN != 'SEM GTIN' and item.prod.cEAN != '':
            product_find = self.env['product.product'].search([
                ('barcode', '=', item.prod.cEAN)], limit=1)

            if product_find:
                product_create['product_id'] = product_find.id

        if not product_find:
            if hasattr(nfe.NFe.infNFe.emit, 'CNPJ'):
                partner_doc = nfe.NFe.infNFe.emit.CNPJ.text
            else:
                partner_doc = nfe.NFe.infNFe.emit.CPF.text

            partner_id = self.env['res.partner'].search([
                ('cnpj_cpf', '=', self.arruma_cpf_cnpj(partner_doc))
            ]).id
            product_code = self.env['product.supplierinfo'].search([
                ('product_code', '=', item.prod.cProd.text),
                ('name', '=', partner_id)
            ], limit=1)
            product_find = self.env['product.product'].browse(product_code.product_tmpl_id.id)

            if product_find:
                product_create['product_id'] = product_find.id

        return self.env['wizard.produtos'].create(product_create)

    def get_partner(self, emit):
        partner_doc = emit.CNPJ if hasattr(emit, 'CNPJ') else emit.CPF
        partner_doc = str(partner_doc)
        partner_doc = self.arruma_cpf_cnpj(partner_doc)
        partner = self.env['res.partner'].search([
            ('cnpj_cpf', '=', partner_doc)])

        # Fornecedor não encontrado, então vamos criar
        if not partner:
            city = self.env['res.state.city'].search([('name', '=ilike', emit.enderEmit.xMun)])
            partner = {
                'name': emit.xNome,
                'is_company': True if hasattr(emit, 'CNPJ') else False,
                'company_type': 'company' if hasattr(emit, 'CNPJ') else 'person',
                'cnpj_cpf': partner_doc,
                'supplier': True,
            }

            if hasattr(emit, 'IE') and hasattr(emit, 'CNPJ'):
                partner['inscr_est'] = emit.IE.text
                partner['indicador_ie_dest'] = '1'
            elif not hasattr(emit, 'IE') and hasattr(emit, 'CNPJ'):
                partner['indicador_ie_dest'] = '9'

            if hasattr(emit, 'xFant'):
                partner['legal_name'] = emit.xFant
            else:
                partner['legal_name'] = emit.xNome

            if hasattr(emit, 'fone'):
                partner['phone'] = emit.enderEmit.fone

            if hasattr(emit, 'xCpl'):
                partner['street2'] = emit.enderEmit.xCpl

            partner['zip'] = emit.enderEmit.CEP
            partner['default_supplier'] = 'supplier'
            partner['street'] = emit.enderEmit.xLgr
            partner['number'] = emit.enderEmit.nro
            partner['district'] = emit.enderEmit.xBairro
            partner['city_id'] = city.id
            partner['state_id'] = city.state_id.id
            partner['country_id'] = self.env.ref('base.br').id
            partner = self.env['res.partner'].create(partner)

        return partner

    def retorna_data(self, date):
        day = str(date).split('T')
        hour = day[1].split('-')
        datehour = day[0] + ' ' + hour[0]
        datetime_obj = datetime.strptime(datehour, '%Y-%m-%d %H:%M:%S')

        return datetime_obj
