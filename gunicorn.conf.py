import os
bind = '0.0.0.0:' + os.environ.get('PORT','8000')
workers = 1
threads = 8
timeout = 90
accesslog = '-'
errorlog = '-'
# Run exactly one background mail/payment worker separately.
