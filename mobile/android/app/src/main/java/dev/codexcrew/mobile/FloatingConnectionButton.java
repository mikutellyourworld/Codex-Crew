package dev.codexcrew.mobile;

import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.view.MotionEvent;
import android.view.ViewConfiguration;
import android.widget.Button;
import android.widget.FrameLayout;

/** A bounded, accessible tap target whose drag position survives screen resizing. */
public final class FloatingConnectionButton extends Button {
    private final SharedPreferences preferences;
    private final FrameLayout container;
    private final int slop;
    private float fractionX, fractionY, downX, downY, initialX, initialY;
    private boolean dragging;

    public FloatingConnectionButton(Context context, FrameLayout container,
            SharedPreferences preferences, Runnable open) {
        super(context);
        this.container = container;
        this.preferences = preferences;
        slop = ViewConfiguration.get(context).getScaledTouchSlop();
        fractionX = preferences.getFloat("connection_x", 1f);
        fractionY = preferences.getFloat("connection_y", .25f);
        setText("ADB");
        setTextSize(12);
        setAllCaps(false);
        setPadding(0, 0, 0, 0);
        setMinWidth(0);
        setMinHeight(0);
        setContentDescription(context.getString(R.string.connection));
        setAlpha(.5f);
        setTextColor(Color.WHITE);
        GradientDrawable background = new GradientDrawable();
        background.setColor(Color.rgb(35, 41, 57));
        background.setShape(GradientDrawable.OVAL);
        setBackground(background);
        setOnClickListener(v -> open.run());
        container.addOnLayoutChangeListener((v, l, t, r, b, ol, ot, or, ob) -> reposition());
        addOnLayoutChangeListener((v, l, t, r, b, ol, ot, or, ob) -> reposition());
    }

    private float maxX() { return Math.max(0, container.getWidth() - getWidth()); }
    private float maxY() { return Math.max(0, container.getHeight() - getHeight()); }
    private float bounded(float value, float max) { return Math.max(0, Math.min(value, max)); }
    private void reposition() {
        setX(bounded(fractionX * maxX(), maxX()));
        setY(bounded(fractionY * maxY(), maxY()));
    }

    @Override public boolean onTouchEvent(MotionEvent event) {
        switch (event.getActionMasked()) {
            case MotionEvent.ACTION_DOWN:
                downX = event.getRawX(); downY = event.getRawY();
                initialX = getX(); initialY = getY(); dragging = false;
                setPressed(true);
                container.requestDisallowInterceptTouchEvent(true);
                return true;
            case MotionEvent.ACTION_MOVE:
                float dx = event.getRawX() - downX, dy = event.getRawY() - downY;
                if (Math.hypot(dx, dy) > slop) dragging = true;
                if (dragging) {
                    setPressed(false);
                    setX(bounded(initialX + dx, maxX()));
                    setY(bounded(initialY + dy, maxY()));
                }
                return true;
            case MotionEvent.ACTION_UP:
                setPressed(false);
                container.requestDisallowInterceptTouchEvent(false);
                if (dragging) {
                    fractionX = maxX() == 0 ? 0 : getX() / maxX();
                    fractionY = maxY() == 0 ? 0 : getY() / maxY();
                    preferences.edit().putFloat("connection_x", fractionX)
                            .putFloat("connection_y", fractionY).apply();
                } else performClick();
                return true;
            case MotionEvent.ACTION_CANCEL:
                setPressed(false);
                container.requestDisallowInterceptTouchEvent(false);
                reposition();
                return true;
            default: return super.onTouchEvent(event);
        }
    }

    @Override public boolean performClick() { return super.performClick(); }
}
