from setuptools import setup


setup(
    name='cairo_dap',
    entry_points={
        'console_scripts': [
            'cairo-dap=cairo_dap.cli:main'
        ]
    }
)