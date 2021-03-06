import base64
from lxml import objectify
from datetime import datetime
import logging
from odoo import api, models, fields, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)
STATE = {'edit': [('readonly', False)]}


class WizardProdutos(models.TransientModel):
    _name = 'wizard.produtos'

    product_id = fields.Many2one('product.product', string="Produto do Odoo")
    name = fields.Char(string="Produto da NFe")
    fator = fields.Many2one(
        'fator.conversao', string=u'Fator de conversão', states=STATE)
    uom_int = fields.Many2one(
        'product.uom', string=u'Unidade Medida do Estabelicmento', states=STATE)
    uom_ext = fields.Many2one(
        'product.uom', string=u'Unidade Medida do XML', states=STATE)
    ncm = fields.Many2one(
        'product.fiscal.classification', string=u'NCM', states=STATE)


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

    @api.multi
    def action_import_nfe_purchase(self):
        if not self.nfe_xml:
            raise UserError('Por favor, insira um arquivo de NFe.')
        nfe_string = base64.b64decode(self.nfe_xml)
        nfe = objectify.fromstring(nfe_string)

        if not hasattr(nfe, 'NFe'):
            raise UserError('Lamento, mas isso não é uma nota fiscal valida.')

        #company = self.get_partner(partner_find=nfe.NFe.infNFe.dest)
        #if not company:
        #    raise UserError("Essa nota não é sua ou seu emitente não esta configurado corretamente.")

        # Carregando fornecedor / Criando
        partner = self.get_partner(partner_find=nfe.NFe.infNFe.emit, create=True, supplier=True)

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
            company_id=1,
            date_approve=self.retorna_data(nfe.NFe.infNFe.ide.dhEmi),
            date_planned=self.retorna_data(nfe.NFe.infNFe.ide.dhEmi),
            date_order=self.retorna_data(nfe.NFe.infNFe.ide.dhEmi),
            payment_term_id=self.payment_term_id.id,
            fiscal_position_id=self.fiscal_position_id.id if self.fiscal_position_id else False,
            partner_ref=nfe.NFe.infNFe.ide.nNF,
            nfe_num=nfe.NFe.infNFe.ide.nNF,
            nfe_emissao=self.retorna_data(nfe.NFe.infNFe.ide.dhEmi),
            nfe_serie=nfe.NFe.infNFe.ide.serie,
            nfe_modelo=nfe.NFe.infNFe.ide.mod,
            nfe_chave=nfe.protNFe.infProt.chNFe,
            state='purchase',
            total_bruto=nfe.NFe.infNFe.total.ICMSTot.vNF,
            total_desconto=nfe.NFe.infNFe.total.ICMSTot.vDesc,
            total_despesas=nfe.NFe.infNFe.total.ICMSTot.vOutro,
            total_seguro=nfe.NFe.infNFe.total.ICMSTot.vSeg,
            total_frete=nfe.NFe.infNFe.total.ICMSTot.vFrete,
            picking_count=1,
            amount_tax=(
                    nfe.NFe.infNFe.total.ICMSTot.vICMS +
                    nfe.NFe.infNFe.total.ICMSTot.vST +
                    nfe.NFe.infNFe.total.ICMSTot.vIPI +
                    nfe.NFe.infNFe.total.ICMSTot.vPIS +
                    nfe.NFe.infNFe.total.ICMSTot.vCOFINS
            ),
        )

        if hasattr(nfe.NFe.infNFe, 'infAdic') and hasattr(nfe.NFe.infNFe.infAdic, 'infCpl'):
            nota_dict['notes'] = nfe.NFe.infNFe.infAdic.infCpl.text
        nota = self.env['purchase.order'].create(nota_dict)

        # Cria os itens na nota
        items = self.purchase_order_line(order=nota,
                                         itens=nfe.NFe.infNFe.det,
                                         dest=nfe.NFe.infNFe.dest)

        # Vamos alterar inserir os itens criados na nota
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

        # Verificando se a unidade medida interna foi informada
        if produto_wizard.uom_int:
            vals['product_uom_xml_id'] = produto_wizard.uom_int.id
        else:
            raise UserError('A unidade medida interna do produto: ' + produto_wizard.name + ' é obrigatoria')

        # Verificando se o ncm foi informado
        if produto_wizard.ncm:
            vals['product_uom_xml_id'] = produto_wizard.uom_int.id
        else:
            raise UserError('O NCM do produto: ' + produto_wizard.name + ' é obrigatorio')

        if hasattr(produto_xml, 'CEST'):
            vals['cest'] = produto_xml.CEST

        if hasattr(produto_xml, 'rastro'):
            vals['tracking'] = 'lot'
        else:
            vals['tracking'] = 'none'

        vals['fiscal_classification_id'] = produto_wizard.ncm.id
        product_id = self.env['product.product'].create(vals)
        return product_id

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

            pf_ids = self.env['product.fiscal.classification'].search([('code', '=', item.prod.NCM)])
            if len(pf_ids) == 1:
                product_create['ncm'] = pf_ids.id
        return self.env['wizard.produtos'].create(product_create)

    def checa_produtos(self):
        if not self.nfe_xml:
            raise UserError('Por favor, insira um arquivo de NFe.')
        nfe_string = base64.b64decode(self.nfe_xml)
        nfe = objectify.fromstring(nfe_string)

        if not hasattr(nfe, 'NFe'):
            raise UserError('Lamento, mas isso não é uma nota fiscal valida.')

        #company = self.get_partner(partner_find=nfe.NFe.infNFe.dest)
        #if not company:
        #    raise UserError("Essa nota não é sua ou seu emitente não esta configurado corretamente.")

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

    def fatura(self, purchase_order, total, itens):
        invoice_env = self.env['account.invoice']
        ipi_base = 0.0
        pis_base = 0.0
        confins_base = 0.0
        for item in itens:
            if hasattr(item.imposto, 'IPI') and hasattr(item.imposto.IPI, 'IPITrib'):
                ipi_base += item.imposto.IPI.IPITrib.vBC
            if hasattr(item.imposto, 'PIS') and hasattr(item.imposto.PIS, 'PISAliq'):
                pis_base += item.imposto.PIS.PISAliq.vBC
            if hasattr(item.imposto, 'COFINS') and hasattr(item.imposto.COFINS, 'COFINSAliq'):
                confins_base += item.imposto.COFINS.COFINSAliq.vBC

        invoice_dict = dict(
            origin=purchase_order.name,
            type='in_invoice',
            comment=u'FATURA GERADA AUTOMATICAMENTE ATRAVES DE IMPORATACAO DE DOCUMENTO ELETRONICO\n'
                    u'CHAVE DA NFE DE ORIGEM: ' + purchase_order.chave_nfe,
            fiscal_comment=purchase_order.notes,
            state='open',
            partner_id=purchase_order.partner_id.id,
            commercial_partner_id=purchase_order.partner_id.id,
            purchase_id=purchase_order.id,  # Pedido de Compras
            date_invoice=purchase_order.date_order,  # Data de Emissao da NF-e
            journal_id=2,  # Diário Contábil :TODO: CRIAR MODELO OPERACAO
            account_id=13,  # Conta Contábil :TODO: CRIAR MODELO OPERACAO
            amount_untaxed=purchase_order.amount_untaxed,  # VALORES TOTAIS DA INVOICE
            amount_untaxed_signed=purchase_order.amount_untaxed,  # VALORES TOTAIS DA INVOICE
            amount_tax=purchase_order.amount_tax,  # Total de Imposto
            currency_id=purchase_order.currency_id,  # Moeda a ser usada
            total_bruto=purchase_order.total_bruto,
            total_desconto=purchase_order.total_desconto,
            icms_base=total.ICMSTot.vBC,
            icms_value=total.ICMSTot.vICMS,
            icms_st_base=total.ICMSTot.vBCST,
            icms_st_value=total.ICMSTot.vST,
            ipi_base=ipi_base,
            ipi_value=total.ICMSTot.vIPI,
            pis_base=pis_base,
            pis_value=total.ICMSTot.vPIS,
            cofins_base=confins_base,
            cofins_value=total.ICMSTot.vCOFINS,
            icms_des_value=total.ICMSTot.vICMSDeson,
        )
        invoice = invoice_env.create(invoice_dict)
        return invoice

    def itens_fatura(self, fatura, order):
        for x in order.order_line:
            item = dict(
                purchase_line_id=order.id,
                invoice_id=fatura.id,
                account_id=24,
                cfop_id=x.cfop.id,
                name=x.product_id.name,
                origin=x.order_id.name,
                uom_id=x.product_uom.id,
                product_id=x.product_id.id,
                price_unit=x.price_unit,
                price_subtotal=x.price_subtotal,
                price_total=0
            )

    def get_partner(self, partner_find, create=False, custumer=False, supplier=False):
        partner_doc = partner_find.CNPJ if hasattr(partner_find, 'CNPJ') else partner_find.CPF
        partner_doc = str(partner_doc)
        partner_doc = self.arruma_cpf_cnpj(partner_doc)
        partner = self.env['res.partner'].search([
            ('cnpj_cpf', '=', partner_doc)])

        # Empresa não encontrada, devemos criar ?
        if not partner and create:
            # Ok, então vamos criar a empresa
            city = self.env['res.state.city'].search([('name', '=ilike', partner_find.enderEmit.xMun)])
            partner = {
                'name': partner_find.xNome,
                'is_company': True if hasattr(partner_find, 'CNPJ') else False,
                'company_type': 'company' if hasattr(partner_find, 'CNPJ') else 'person',
                'cnpj_cpf': partner_doc,
                'supplier': True,
            }

            if custumer:
                partner['custumer'] = True

            if supplier:
                partner['supplier'] = True

            if hasattr(partner_find, 'IE') and hasattr(partner_find, 'CNPJ'):
                partner['inscr_est'] = partner_find.IE.text
                partner['indicador_ie_dest'] = '1'
            elif not hasattr(partner_find, 'IE') and hasattr(partner_find, 'CNPJ'):
                partner['indicador_ie_dest'] = '9'

            if hasattr(partner_find, 'xFant'):
                partner['legal_name'] = partner_find.xFant
            else:
                partner['legal_name'] = partner_find.xNome

            if hasattr(partner_find, 'fone'):
                partner['phone'] = partner_find.enderEmit.fone

            if hasattr(partner_find, 'xCpl'):
                partner['street2'] = partner_find.enderEmit.xCpl

            partner['zip'] = partner_find.enderEmit.CEP
            partner['default_supplier'] = 'supplier'
            partner['street'] = partner_find.enderEmit.xLgr
            partner['number'] = partner_find.enderEmit.nro
            partner['district'] = partner_find.enderEmit.xBairro
            partner['city_id'] = city.id
            partner['state_id'] = city.state_id.id
            partner['country_id'] = self.env.ref('base.br').id
            partner = self.env['res.partner'].create(partner)

        return partner

    def create_tax(self, tax, aliquota):
        taxes = self.env['account.tax']
        names = {
            'icms': 'ICMS Entrada',
            'icmsst': 'ICMS ST Entrada',
            'ipi': 'IPI Entrada',
            'pis': 'PIS Entrada',
            'cofins': 'COFINS Entrada',
        }
        tax_id = taxes.search(
            [
                ('domain', '=', tax),
                ('amount', '=', aliquota),
                ('type_tax_use', '=', 'purchase'),
                ('active', '=', True)
            ]
        )
        if not tax_id:
            tax_vals = dict(
                name=names[tax] + ' ' + str(aliquota) + '%',
                type_tax_use='purchase',
                amount_type='icmsst' if tax == 'icmsst' else 'division',
                price_include=True if tax not in ['icmsst', 'ipi'] else False,
                amount=aliquota,
                description=names[tax] + ' ' + str(aliquota) + '%',
                tax_exigibility='on_invoice',
                domain=tax,
                active=True
            )
            tax_id = taxes.create(tax_vals)
        return tax_id.id

    def purchase_order_line(self, order, itens, dest):
        # Variaveis uteis
        items = []
        cont = 1

        # Criando produtos na nota
        for produto in self.wizard_produtos:
            for prod in itens:
                if produto.name == prod.prod.xProd:
                    taxas = []
                    # Definindo variaveis de acordo com produto, pode muda com fator
                    quantidade = prod.prod.qCom
                    preco_unitario = prod.prod.vUnCom

                    # Verificando se o produto tem fator de conversão
                    if hasattr(produto.fator, 'id'):
                        # Aplicando fator de conversão
                        if produto.fator.tipo == '0':
                            quantidade = quantidade * produto.fator.valor
                        elif produto.fator.tipo == '1':
                            quantidade = quantidade / produto.fator.valor
                        preco_unitario = prod.prod.vProd / quantidade

                    # Verificando se a unidade medida externa foi informada
                    if not produto.uom_ext:
                        raise UserError('A unidade medida do XML do produto: ' + produto.name + ' é obrigatoria')

                    # Verificando se o produto foi relacionado
                    if not produto.product_id:
                        # Cadastrando produto
                        produto.product_id = self.cadastro_de_produto(produto, prod.prod, preco_unitario)

                    # Pesquisando relacionamentos do produto
                    product_code = self.env['product.supplierinfo'].search([
                        ('product_code', '=', prod.prod.cProd.text),
                        ('name', '=', order.partner_id.id)
                    ], limit=1)

                    # Verificando se o produto ja possui algum relacionamento com o fornecedor
                    if not product_code:
                        # Cadastrando relacionamento
                        self.relacionamento_produto_fornecedor(order.partner_id, produto, prod.prod)

                    # Pesquisando cfop da nota
                    cfop = self.env['br_account.cfop'].search([
                        ('code', '=', prod.prod.CFOP)], limit=1)
                    if not cfop:
                        raise UserError("CFOP Não escontrado, favor verificar")

                    purchase_order_line_dict = {
                        'product_id': produto.product_id.id,
                        'name': prod.prod.xProd,
                        'date_planned': order.date_approve,
                        'product_qty': quantidade,
                        'price_unit': preco_unitario,
                        'product_uom': produto.uom_int.id,
                        'order_id': order.id,
                        'partner_id': order.partner_id.id,
                        'product_uom_xml': produto.uom_ext.id,
                        'cfop_id': cfop.id,
                        'valor_bruto': prod.prod.vProd,
                        'num_item_xml': cont,
                    }

                    # Configurando o ICMS e suas particularidades
                    icms = prod.imposto.ICMS.getchildren()[0]
                    if hasattr(icms, 'CSOSN'):
                        purchase_order_line_dict['icms_csosn_simples'] = icms.CSOSN

                    if hasattr(icms, 'CST'):
                        purchase_order_line_dict['icms_cst_normal'] = icms.CST

                    if hasattr(icms, 'pICMS'):
                        purchase_order_line_dict['aliquota_icms_proprio'] = icms.pICMS
                        taxas.append(self.create_tax(tax='icms', aliquota=icms.pICMS))

                    if hasattr(icms, 'pMVAST'):
                        purchase_order_line_dict['icms_st_aliquota_mva'] = icms.pMVAST

                    if hasattr(icms, 'pRedBCST'):
                        purchase_order_line_dict['icms_st_aliquota_reducao_base'] = icms.pRedBCST

                    # Configurando o IPI e suas particularidades
                    if hasattr(prod.imposto, 'IPI'):
                        if hasattr(prod.imposto.IPI, 'IPINT'):
                            purchase_order_line_dict['ipi_cst'] = prod.imposto.IPI.IPINT.CST
                        else:
                            taxas.append(self.create_tax(tax='ipi', aliquota=prod.imposto.IPI.IPITrib.pIPI))
                            purchase_order_line_dict['ipi_cst'] = prod.imposto.IPI.IPITrib.CST
                            # Vamos verificar a Constituição (art. 155, §2°, XI) e Lei Kandir (LC 87/96, art. 13, §2°)
                            # Verificando se esse produto não vai ter ipi na base por Industrialização
                            if hasattr(icms, 'vICMS') and icms.vICMS > 0 and \
                                    dest.indIEDest == 1 and cfop.name.count("Industrialização") > 0:
                                purchase_order_line_dict['incluir_ipi_base'] = False

                            # Verificando se esse produto não vai ter ipi na base por Comercialização
                            elif hasattr(icms, 'vICMS') and icms.vICMS > 0 and \
                                    dest.indIEDest == 1 and cfop.name.count("Comercialização") > 0:
                                purchase_order_line_dict['incluir_ipi_base'] = False

                            # Produto vai ter a ipi na base
                            else:
                                purchase_order_line_dict['incluir_ipi_base'] = True

                    # Configurando o pis
                    if hasattr(prod.imposto, 'PIS'):
                        if hasattr(prod.imposto.PIS, 'PISAliq'):
                            purchase_order_line_dict['pis_cst'] = prod.imposto.PIS.PISAliq.CST
                            taxas.append(self.create_tax(tax='pis', aliquota=prod.imposto.PIS.PISAliq.pPIS))
                        else:
                            purchase_order_line_dict['pis_cst'] = prod.imposto.PIS.PISNT.CST

                    # Configurando o confins
                    if hasattr(prod.imposto, 'COFINS'):
                        if hasattr(prod.imposto.PIS, 'COFINSAliq'):
                            purchase_order_line_dict['cofins_cst'] = prod.imposto.COFINS.COFINSAliq.CST
                            taxas.append(self.create_tax(tax='confins', aliquota=prod.imposto.PIS.COFINSAliq.pCOFINS))
                        elif hasattr(prod.imposto.COFINS, 'COFINSNT'):
                            purchase_order_line_dict['cofins_cst'] = prod.imposto.COFINS.COFINSNT.CST

                    if hasattr(prod.prod, 'vDesc'):
                        purchase_order_line_dict['valor_desconto'] = prod.prod.vDesc

                    if hasattr(prod.prod, 'vSeg'):
                        purchase_order_line_dict['valor_seguro'] = prod.prod.vSeg

                    if hasattr(prod.prod, 'vOutro'):
                        purchase_order_line_dict['outras_despesas'] = prod.prod.vOutro

                    if hasattr(prod.prod, 'vFrete'):
                        purchase_order_line_dict['valor_frete'] = prod.prod.vFrete

                    purchase_order_line_dict['taxes_id'] = [(6, _, taxas)]
                    purchase_order_line = self.env['purchase.order.line'].create(purchase_order_line_dict)

                    items.append((4, purchase_order_line.id, False))
                    cont += 1

        return items

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

    @staticmethod
    def retorna_data(date):
        data = str(date).split('T')
        hora = data[1].split('-')
        data_hora = data[0] + ' ' + hora[0]
        datetime_obj = datetime.strptime(data_hora, '%Y-%m-%d %H:%M:%S')

        return datetime_obj
