import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
README = """trac.por
=============

for more details visit: http://getpenelope.github.com/"""
CHANGES = open(os.path.join(here, 'CHANGES.txt')).read()

requires = [
    'Trac',
    'TracThemeEngine>=2.0',
    'TracXMLRPC',
    'TracDynamicFields',
    'sensitivetickets>=0.21',
    'privatecomments',
    'por.models'
    ]


extra = {} 
try:
    from trac.util.dist import get_l10n_cmdclass 
    cmdclass = get_l10n_cmdclass() 
    if cmdclass: # Yay, Babel is there, we've got something to do! 
        extra['cmdclass'] = cmdclass 
        extractors = [ 
            ('**.py',                'python', None), 
            ('**/templates/**.html', 'genshi', None), 
            ('**/templates/**.txt',  'genshi', { 
                'template_class': 'genshi.template:TextTemplate' 
            }), 
        ] 
        extra['message_extractors'] = { 
            'trac/por': extractors, 
        }
except ImportError: 
    pass 



setup(name='trac.por',
      version='1.2.5',
      description='Penelope: trac integration',
      long_description=README + '\n\n' +  CHANGES,
      classifiers=[
        "Programming Language :: Python",
        "Framework :: Trac",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
        ],
      author='Penelope Team',
      author_email='penelopedev@redturtle.it',
      url='https://getpenelope.github.com',
      keywords='web trac',
      namespace_packages=['trac'],
      test_suite='trac.por.tests',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      install_requires = requires,
      entry_points = {
       'trac.plugins': [
            'trac.por = trac.por.plugins',
            'trac.por.users = trac.por.user',
            'trac.por.communication = trac.por.communication',
            'trac.por.workflow = trac.por.workflow',
        ],
      },
      **extra
      )

