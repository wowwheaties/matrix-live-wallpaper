// Mutter refuses restack requests from clients for DESKTOP-layer windows,
// so the wallpaper player cannot lower itself below the desktop-icons
// window (DING on Ubuntu, or any other desktop-type window). From inside
// the shell, Meta.Window.lower()/raise() bypass that filtering.
import Meta from 'gi://Meta';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

export default class MatrixWallpaperBelow extends Extension {
    enable() {
        this._busy = false;
        this._restackedId = global.display.connect('restacked',
            () => this._fixOrder());
        this._fixOrder();
    }

    disable() {
        if (this._restackedId) {
            global.display.disconnect(this._restackedId);
            this._restackedId = null;
        }
    }

    _fixOrder() {
        if (this._busy)
            return;
        this._busy = true;
        try {
            const actors = global.get_window_actors();
            let matrixIdx = -1, matrixWin = null;
            for (let i = 0; i < actors.length; i++) {
                const win = actors[i].meta_window;
                if (win && win.get_title() === 'matrix-wallpaper') {
                    matrixIdx = i;
                    matrixWin = win;
                    break;
                }
            }
            if (!matrixWin || matrixIdx === 0)
                return;
            // push the wallpaper down, and lift any other desktop-layer
            // window (e.g. the icons window) that is still stuck under it
            matrixWin.lower();
            for (let i = 0; i < matrixIdx; i++) {
                const win = actors[i].meta_window;
                if (win && win.get_layer() === Meta.StackLayer.DESKTOP)
                    win.raise();
            }
        } finally {
            this._busy = false;
        }
    }
}
