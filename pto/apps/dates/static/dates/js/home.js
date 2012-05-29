$(function() {
  $('#calendar').fullCalendar({
    editable: false,
    //events: "/calendar/events/",
    events: function(start, end, callback) {
      var ops = {start: start.getTime(), end: end.getTime()};
      $.getJSON('/calendar/events/', ops, function(response) {
        callback(response.events);
        var c = 0;
        $.each(response.colors, function() { c++; });
        var container = $('#calendar-legend');
        if (container.size()) {
          // reset all
          $('span', container).remove();
          $('strong', container).hide();
        } else {
          // set up container
          container = $('<div id="calendar-legend">');
          $('<strong>')
            .text('Legend:')
              .appendTo(container);
          $('<a href="/following/">')
            .addClass('following-link')
              .html('Manage people you follow &rarr;')
                .appendTo(container);
          container.insertAfter('#calendar table.fc-header');
        }
        if (c > 0) {
          $('strong', container).show();
        }
        $.each(response.colors, function(i, each) {
          $('<span>')
            .text(each.name)
              .css('background-color', each.color)
                .css('color', '#fff')
                  .insertBefore($('a.following-link', container));
        });
      });
    },
    firstDay: CALENDAR_FIRST_DAY,
    selectable: true,
    selectHelper: true,
    select: function(start, end, allDay) {
      // convert timezoneoffset from minutes to milliseconds
      var tzd = new Date().getTimezoneOffset() * 1000 * 60;
      var start_ts = start.getTime() + tzd;
      var end_ts = end.getTime() + tzd;
      url = '/notify/?start=' + start_ts + '&end=' + end_ts;
      location.href = url;
      //calendar.fullCalendar('unselect');
    },
    eventClick: function(event) {
      if (!event.mine) return;
      $('#dialog-edit a')
        .attr('href', '/notify/?start=' + event.start.getTime() + '&end=' + event.end.getTime());
      $('#dialog-edit').dialog('open');
    }
  });

  /*
  $('<a href="#rightnow"></a>')
    .html($('#rightnow h2').text() + ' &darr;')
      .addClass('anchor')
        .prependTo($('#content'));
   */

  $('<a href="#pto_taken"></a>')
    .html($('#pto_taken h2').text() + ' &darr;')
      .addClass('anchor')
        .prependTo($('#content'));

  $('#dialog-edit').dialog({
     autoOpen: false
  });


});
