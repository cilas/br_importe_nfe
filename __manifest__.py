# -*- coding: utf-8 -*-
{
    'name': 'Importador de NF-e',

    'summary': 'Importado de Compra via xml do nfe e Manifestação do Usuario',

    'description': """
        Esse modulo foi desenvolvido para trabalhar importando NF-e via XML ou Manifestação do Usuario de 
       forma bem simples e concreta em vista da sefaz.
    """,

    'author': "Implanti Soluções",
    'website': "http://www.implanti.com.br",
    'category': 'purchase',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': [
        'purchase',
        'account_invoicing',
    ],

    # always loaded
    'data': [
        'views/views.xml',
    ]
}