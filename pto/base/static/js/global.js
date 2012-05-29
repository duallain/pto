$(function() {
  $('.flash a.close').click(function() {
    $(this).parent('.flash').fadeOut(500);
    return false;
  });

  if ($('.flash:visible').size()) {
    setTimeout(function() {
      $('.flash:visible').fadeOut(500);
    }, 10 * 1000);
  }
});
