from django.urls import path

from _bq_core.dj.views.get_entries import BQGetTableDataView
from _bq_core.dj.views.upsert import BQBatchUpsertView

app_name = 'bq'
urlpatterns = [
    path('upsert/', BQBatchUpsertView.as_view()),
    path('get/', BQGetTableDataView.as_view()),
]
