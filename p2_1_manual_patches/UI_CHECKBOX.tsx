{/* Insert this JSX block under the "Recording retention days" Input field. */}
{/* Look for the closing </div> after the retention input and add this above it. */}

<div className="space-y-2 border-t border-border pt-3">
  <label className="flex items-start gap-2">
    <input
      type="checkbox"
      checked={useDeepstream}
      onChange={(e) => setUseDeepstream(e.target.checked)}
      disabled={!canEdit}
      className="mt-0.5 h-4 w-4 rounded border-border"
    />
    <div>
      <p className="text-sm font-medium text-foreground">
        {t('settings.deepstream.label')}
      </p>
      <p className="text-xs text-muted-foreground">
        {t('settings.deepstream.description')}
      </p>
    </div>
  </label>
</div>
