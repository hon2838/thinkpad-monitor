"""Render reproducible offscreen UI evidence using synthetic test telemetry.

Run from any directory with the desktop extra installed. The optional first
argument is the evidence output directory; --refresh-readme replaces the
repository preview. QT_SCALE_FACTOR=2 exercises Qt's logical scaling.
These images do not represent KDE/GNOME sessions or physical hardware.
"""
import os, sys, time
from pathlib import Path
os.environ['QT_QPA_PLATFORM']='offscreen'
root = Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root / 'src'), str(root / 'tests')]
from PySide6 import QtCore, QtGui, QtWidgets
from thinkpad_monitor.desktop import MonitorWindow
from test_desktop import FakeCollector, make_sample, wait_for
app=QtWidgets.QApplication([])
app.setStyle('Fusion')
base=app.palette()
arguments = [arg for arg in sys.argv[1:] if arg != '--refresh-readme']
out = str(Path(arguments[0] if arguments else root / 'build' / 'ui-previews').resolve())
Path(out).mkdir(parents=True, exist_ok=True)
for dark,font,size,name in [(False,10,(1100,800),'light'),(True,10,(1100,800),'dark'),(False,14,(480,640),'narrow-large'),(True,14,(1024,600),'dark-large'),(False,14,(360,600),'minimum-large')]:
    palette=QtGui.QPalette(base)
    if dark:
        for role,color in [('Window','#292b30'),('WindowText','#eff0f1'),('Base','#202226'),('AlternateBase','#34373c'),('Text','#eff0f1'),('Button','#34373c'),('ButtonText','#eff0f1'),('Highlight','#3daee9'),('HighlightedText','#111111'),('Mid','#74777d'),('Midlight','#44474d'),('PlaceholderText','#b7b9be')]:
            palette.setColor(getattr(QtGui.QPalette.ColorRole,role),QtGui.QColor(color))
    app.setPalette(palette)
    f=app.font(); f.setPointSize(font); app.setFont(f)
    w=MonitorWindow(FakeCollector(),interval=60)
    w.resize(*size); w.show()
    if not wait_for(lambda:w.last_sample is not None and not w._sampling,app=app):
        w.shutdown()
        raise RuntimeError('Synthetic preview collector did not finish')
    w.toggle_pause()
    w._graph.clear()
    profiles = [('_graph', 42), ('_cpu_detail_graph', 42), ('_mem_graph', 50),
                ('_storage_graph', (1000, 2000)), ('_battery_graph', 10),
                ('_net_graph', (100, 50)), ('_therm_graph', 55),
                ('_fan_graph', 2500), ('_power_graph', 12.5), ('_gpu_graph', 10)]
    start = time.monotonic() - 38
    for attr, values in profiles:
        graph = getattr(w, attr)
        graph.clear()
        for i in range(20):
            factor = 0.6 + 0.4 * i / 19
            if isinstance(values, tuple):
                graph.append(*(v * factor for v in values), timestamp=start + i * 2)
            else:
                graph.append(values * factor, timestamp=start + i * 2)
    app.processEvents()
    w.grab().save(out+'/'+name+'.png')
    if '--refresh-readme' in sys.argv and name in ('dark', 'narrow-large'):
        w.grab().save(str(root / 'docs' / ('desktop-preview-' + name + '.png')))
    w._graph.setFocus(QtCore.Qt.FocusReason.TabFocusReason)
    app.processEvents()
    w._graph.grab().save(out+'/'+name+'-graph-focus.png')
    w._pause_button.setFocus()
    w._tabs.currentWidget().verticalScrollBar().setValue(0)
    app.processEvents()
    print(name,'actual',w.width(),w.height(),'minimum',w.minimumSizeHint().width(),w.minimumSizeHint().height())
    w._select_page(1); w._focus_filter(); app.processEvents(); w._cpu_table.filter_edit.setText('Core'); app.processEvents()
    def filter_is_visible():
        viewport = w._tabs.currentWidget().viewport()
        search = w._cpu_table.filter_edit
        y = search.mapTo(viewport, QtCore.QPoint(0, 0)).y()
        return y >= 0 and y + search.height() <= viewport.height()
    if not wait_for(filter_is_visible, app=app):
        w.shutdown()
        raise RuntimeError('The focused filter did not scroll into view')
    w.grab().save(out+'/'+name+'-table.png')
    if name=='light':
        # Render the live status without scheduling more samples: all preview
        # graph times above are synthetic and must remain in one clock domain.
        w._select_page(0); w._paused = False; w._pause_button.setText('Pause')
        w._refresh_icons()
        w._update_status(); app.processEvents()
        w._tabs.currentWidget().verticalScrollBar().setValue(0)
        if '--refresh-readme' in sys.argv:
            w.grab().save(str(root / 'docs' / 'desktop-preview.png'))
            for page, slug in enumerate(('overview', 'processor', 'memory', 'storage',
                                         'batteries', 'network', 'thermals', 'graphics', 'power')):
                w._select_page(page)
                app.processEvents()
                w._tabs.currentWidget().verticalScrollBar().setValue(0)
                app.processEvents()
                w.grab().save(str(root / 'docs' / ('preview-' + slug + '.png')))
            w._select_page(0)
        w._on_failure('Example sensor timeout'); app.processEvents(); w.grab().save(out+'/error.png')
        w._on_sample(make_sample())
        w._last_updated=time.monotonic()-181; w._update_status(); app.processEvents()
        w.grab().save(out+'/stale.png')
    w.shutdown(); w.close(); app.processEvents()
