INFO:app:Upload folder configured: /tmp/upload_files
INFO:app:✓ Registered auth_bp
INFO:app:✓ Registered main_bp
INFO:app:✓ Registered supervisor_bp
INFO:app:✓ Registered employee_bp
WARNING:app:✗ Could not import blueprints.schedule_management: No module named 'blueprints.schedule_management'
WARNING:app:✗ Could not import blueprints.time_off_management: No module named 'blueprints.time_off_management'
WARNING:app:✗ Could not import blueprints.shift_swap: No module named 'blueprints.shift_swap'
WARNING:app:✗ Could not import blueprints.overtime_opportunities: No module named 'blueprints.overtime_opportunities'
WARNING:app:✗ Could not import blueprints.employee_dashboard: No module named 'blueprints.employee_dashboard'
WARNING:app:✗ Could not import blueprints.fatigue_tracking: No module named 'blueprints.fatigue_tracking'
WARNING:app:✗ Could not import blueprints.holiday_management: No module named 'blueprints.holiday_management'
WARNING:app:✗ Could not import blueprints.position_messages: No module named 'blueprints.position_messages'
WARNING:app:✗ Could not import blueprints.sleep_tracking: No module named 'blueprints.sleep_tracking'
WARNING:app:✗ Could not import blueprints.maintenance_issues: No module named 'blueprints.maintenance_issues'
WARNING:app:✗ Could not import blueprints.shift_trade_board: No module named 'blueprints.shift_trade_board'
WARNING:app:✗ Could not import blueprints.casual_workers: No module named 'blueprints.casual_workers'
WARNING:app:✗ Could not import blueprints.employee_self_service: No module named 'blueprints.employee_self_service'
WARNING:app:✗ Could not import blueprints.crew_coverage: No module named 'blueprints.crew_coverage'
INFO:app:✓ Registered employee_import_bp
WARNING:app:✗ Could not import blueprints.availability_management: No module named 'blueprints.availability_management'
Traceback (most recent call last):
  File "/opt/render/project/src/.venv/bin/flask", line 8, in <module>
    sys.exit(main())
             ^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/flask/cli.py", line 1063, in main
    cli.main()
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/click/core.py", line 1078, in main
    rv = self.invoke(ctx)
         ^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/click/core.py", line 1682, in invoke
    cmd_name, cmd, args = self.resolve_command(ctx, args)
                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/click/core.py", line 1729, in resolve_command
    cmd = self.get_command(ctx, cmd_name)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/flask/cli.py", line 578, in get_command
    app = info.load_app()
          ^^^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/flask/cli.py", line 312, in load_app
    app = locate_app(import_name, None, raise_if_not_found=False)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/render/project/src/.venv/lib/python3.11/site-packages/flask/cli.py", line 218, in locate_app
    __import__(module_name)
  File "/opt/render/project/src/app.py", line 276, in <module>
    @app.before_first_request
     ^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'Flask' object has no attribute 'before_first_request'. Did you mean: '_got_first_request'?
==> Build failed 😞
==> Common ways to troubleshoot your deploy: https://render.com/docs/troubleshooting-deploy
